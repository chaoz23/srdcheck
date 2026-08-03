"""Query dispatch and the jurisdiction gate.

Every query passes the gate first: if no loaded adapter claims the query
type, or the entity named isn't in any adapter's registry, the answer is an
honest exit 2 — never a guess (T1, T8).
"""

from . import verdict as v
from .adapter import Adapter
from .coverage import apply_query_scope as _scoped
from .house_rules import (MANIFEST_SCHEMA, POLICY_CONTEXT_SCHEMA,
                          attach_lineage, import_manifest, resolve_policy)
from .provenance import (ASSERTED_FACTS_SCHEMA, TABLE_DECISION_SCHEMA,
                         annotate_params)
from .schema import ValidationIssue, issues as schema_issues, normalize_integers

NON_EMPTY_NAME_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1, "pattern": r"\S"},
    },
    "required": ["name"],
    "additionalProperties": False,
}
# Kept as an import-compatible alias for existing jurisdiction integrations.
JURISDICTION_INPUT_SCHEMA = NON_EMPTY_NAME_INPUT_SCHEMA

def validation_refusal(problems, adapter=""):
    """Turn typed validation issues into a structured recovery verdict."""
    unknown = [_input_path(problem.path) for problem in problems
               if problem.code == "additional-property"]
    missing = [_input_path(problem.path) for problem in problems
               if problem.code == "required"]
    data = {"validation_errors": [str(problem) for problem in problems]}
    if unknown:
        data["unknown_fields"] = unknown
    reason_code = ("missing-fact"
                   if all(problem.code == "required" for problem in problems)
                   else "invalid-input")
    return v.cannot_adjudicate(
        "Invalid input; correct the request before adjudication: "
        + "; ".join(data["validation_errors"]),
        adapter=adapter,
        data=data,
        reason_code=reason_code,
        missing_inputs=missing,
    )


class Engine:
    def __init__(self, adapter_paths):
        self.adapters = [Adapter(p) for p in adapter_paths]

    def jurisdiction(self, name):
        problems = schema_issues({"name": name}, NON_EMPTY_NAME_INPUT_SCHEMA)
        if problems:
            return _scoped(self._invalid_input(problems), "kernel", "jurisdiction")
        for a in self.adapters:
            cats = a.lookup_entity(name)
            if cats:
                categories = sorted(set(cats))
                return _scoped(v.legal(
                    f"'{name}' is known content: {', '.join(categories)}.",
                    adapter=a.id,
                    data={"categories": categories}), "kernel", "jurisdiction")
        known = ", ".join(a.id for a in self.adapters)
        return _scoped(v.cannot_adjudicate(
            f"'{name}' is not present in any loaded ruleset ({known}). "
            "Unknown or third-party content cannot be adjudicated.",
            adapter=known,
            reason_code="unsupported-content",
            missing_inputs=[]), "kernel", "jurisdiction")

    def cite(self, name):
        scope = {
            "coverage_level": "registry-only",
            "checked_scope": ["loaded source-heading lookup", "returned source text"],
            "unchecked_scope": ["rules interpretation", "mechanical legality"],
            "assumptions": ["the supplied heading names the source passage the caller intends"],
        }
        problems = schema_issues({"name": name}, NON_EMPTY_NAME_INPUT_SCHEMA)
        if problems:
            return v.with_scope(self._invalid_input(problems), **scope)
        for a in self.adapters:
            hit = a.cite(name)
            if hit:
                return v.with_scope(v.legal(
                    f"Verbatim source text for '{name}' (p.{hit['page']}).",
                    adapter=a.id, data=hit), **scope)
        known = ", ".join(a.id for a in self.adapters)
        return v.with_scope(v.cannot_adjudicate(
            f"'{name}' not found as a heading in any loaded ruleset's source "
            f"text ({known}).", adapter=known,
            reason_code="unsupported-content",
            missing_inputs=[]), **scope)

    def query(self, query_type, params, *, asserted_facts=None,
              table_decision=None, table_policy=None, policy_context=None):
        metadata_problems = []
        if asserted_facts is not None:
            metadata_problems.extend(schema_issues(
                asserted_facts, ASSERTED_FACTS_SCHEMA,
                path="$.asserted_facts"))
        if table_decision is not None:
            metadata_problems.extend(schema_issues(
                table_decision, TABLE_DECISION_SCHEMA,
                path="$.table_decision"))
        if table_policy is not None:
            metadata_problems.extend(schema_issues(
                table_policy, MANIFEST_SCHEMA, path="$.table_policy"))
        if policy_context is not None:
            metadata_problems.extend(schema_issues(
                policy_context, POLICY_CONTEXT_SCHEMA,
                path="$.policy_context"))
        if table_decision is not None and table_policy is not None:
            metadata_problems.append(ValidationIssue(
                "$.table_policy", "conflict",
                "cannot be combined with an explicit table_decision"))
        if metadata_problems:
            return v.with_provenance(
                validation_refusal(metadata_problems), params, consumed=False)
        if asserted_facts is not None:
            try:
                annotate_params(params, asserted_facts)
            except (KeyError, TypeError, ValueError) as exc:
                return v.with_provenance(v.cannot_adjudicate(
                    "Invalid asserted fact metadata: " + str(exc),
                    reason_code="invalid-input", missing_inputs=[],
                    data={"validation_errors": [str(exc)]}), params,
                    consumed=False)

        if table_policy is not None:
            try:
                import_manifest(table_policy)
                table_decision = resolve_policy(
                    query_type, params, table_policy, policy_context)
            except (KeyError, TypeError, ValueError) as exc:
                return v.with_provenance(v.cannot_adjudicate(
                    "Invalid or ambiguous table policy: " + str(exc),
                    reason_code="invalid-input", missing_inputs=[],
                    data={"validation_errors": [str(exc)]}), params,
                    consumed=False)

        def receipt(result, *, consumed=True):
            decision = (attach_lineage(
                table_decision, query_type, result.rule_ids)
                        if consumed else None)
            return v.with_provenance(
                result, params, asserted_facts, decision,
                consumed=consumed)

        if not isinstance(query_type, str) or not query_type.strip():
            return receipt(v.cannot_adjudicate(
                "Query type must be a non-empty string.",
                reason_code="invalid-input", missing_inputs=[]), consumed=False)
        if query_type == "jurisdiction":
            problems = schema_issues(params, NON_EMPTY_NAME_INPUT_SCHEMA)
            if problems:
                return receipt(_scoped(
                    self._invalid_input(problems), "kernel", query_type),
                    consumed=False)
            return receipt(self.jurisdiction(params["name"]))
        for a in self.adapters:
            if query_type in a.query_types:
                schema = (a.query_meta.get(query_type) or {}).get("inputSchema")
                problems = schema_issues(params, schema)
                if problems:
                    return receipt(_scoped(
                        self._invalid_input(problems, a.id),
                        a.manifest["name"], query_type), consumed=False)
                # JSON Schema defines 1 and 1.0 as the same integer. Handlers
                # receive the canonical Python integer in a fresh structure so
                # transport representation cannot change adjudication and the
                # caller's request is never mutated.
                normalized = normalize_integers(params, schema or {})
                handled = a.handle(query_type, normalized)
                if not hasattr(handled, "asserted_facts"):
                    return handled
                return v.with_provenance(
                    handled, normalized,
                    asserted_facts,
                    attach_lineage(table_decision, query_type,
                                   handled.rule_ids))
        known = sorted(t for a in self.adapters for t in a.query_types)
        return receipt(v.cannot_adjudicate(
            f"No loaded adapter answers query type '{query_type}'. "
            f"Available: {', '.join(known)}.",
            adapter=", ".join(a.id for a in self.adapters),
            reason_code="unmodeled-rule",
            missing_inputs=[]), consumed=False)

    _invalid_input = staticmethod(validation_refusal)


def _input_path(json_path):
    """Convert the validator's JSON root notation to a request-relative path."""
    if json_path.startswith("$."):
        return json_path[2:]
    if json_path.startswith("$"):
        return json_path[1:]
    return json_path
