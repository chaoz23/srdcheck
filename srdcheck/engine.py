"""Query dispatch and the jurisdiction gate.

Every query passes the gate first: if no loaded adapter claims the query
type, or the entity named isn't in any adapter's registry, the answer is an
honest exit 2 — never a guess (T1, T8).
"""

from . import verdict as v
from .adapter import Adapter
from .schema import issues as schema_issues, normalize_integers

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
            return self._invalid_input(problems)
        for a in self.adapters:
            cats = a.lookup_entity(name)
            if cats:
                categories = sorted(set(cats))
                return v.legal(
                    f"'{name}' is known content: {', '.join(categories)}.",
                    adapter=a.id,
                    data={"categories": categories})
        known = ", ".join(a.id for a in self.adapters)
        return v.cannot_adjudicate(
            f"'{name}' is not present in any loaded ruleset ({known}). "
            "Unknown or third-party content cannot be adjudicated.",
            adapter=known,
            reason_code="unsupported-content",
            missing_inputs=[])

    def cite(self, name):
        problems = schema_issues({"name": name}, NON_EMPTY_NAME_INPUT_SCHEMA)
        if problems:
            return self._invalid_input(problems)
        for a in self.adapters:
            hit = a.cite(name)
            if hit:
                return v.legal(
                    f"Verbatim source text for '{name}' (p.{hit['page']}).",
                    adapter=a.id, data=hit)
        known = ", ".join(a.id for a in self.adapters)
        return v.cannot_adjudicate(
            f"'{name}' not found as a heading in any loaded ruleset's source "
            f"text ({known}).", adapter=known,
            reason_code="unsupported-content",
            missing_inputs=[])

    def query(self, query_type, params):
        if not isinstance(query_type, str) or not query_type.strip():
            return v.cannot_adjudicate(
                "Query type must be a non-empty string.",
                reason_code="invalid-input", missing_inputs=[])
        if query_type == "jurisdiction":
            problems = schema_issues(params, NON_EMPTY_NAME_INPUT_SCHEMA)
            if problems:
                return self._invalid_input(problems)
            return self.jurisdiction(params["name"])
        for a in self.adapters:
            if query_type in a.query_types:
                schema = (a.query_meta.get(query_type) or {}).get("inputSchema")
                problems = schema_issues(params, schema)
                if problems:
                    return self._invalid_input(problems, a.id)
                # JSON Schema defines 1 and 1.0 as the same integer. Handlers
                # receive the canonical Python integer in a fresh structure so
                # transport representation cannot change adjudication and the
                # caller's request is never mutated.
                return a.handle(
                    query_type, normalize_integers(params, schema or {}))
        known = sorted(t for a in self.adapters for t in a.query_types)
        return v.cannot_adjudicate(
            f"No loaded adapter answers query type '{query_type}'. "
            f"Available: {', '.join(known)}.",
            adapter=", ".join(a.id for a in self.adapters),
            reason_code="unmodeled-rule",
            missing_inputs=[])

    _invalid_input = staticmethod(validation_refusal)


def _input_path(json_path):
    """Convert the validator's JSON root notation to a request-relative path."""
    if json_path.startswith("$."):
        return json_path[2:]
    if json_path.startswith("$"):
        return json_path[1:]
    return json_path
