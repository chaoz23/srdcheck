"""Project one srdcheck verdict into ``table.evaluation/1.0``.

The shared envelope remains self-attested and advisory.  It does not turn a
rules verdict into table, encounter-state, or action-execution authority.
"""

import hashlib
import json

from . import __version__
from .access import capabilities


TABLE_EVALUATION_SCHEMA_VERSION = "table.evaluation/1.0"

CALLER_CONTEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "session_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "entity_refs": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 256},
        },
        "correlation_id": {
            "type": "string", "minLength": 1, "maxLength": 244,
            "description": ("Caller-owned correlation identity; projected as "
                            "subject.entity_refs entry correlation:<id>."),
        },
    },
}

# Self-contained MCP discovery schema. table-kit remains the canonical owner;
# this transport copy deliberately describes the full envelope shape without
# claiming host attestation or importing a runtime dependency.
TABLE_EVALUATION_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "evaluation_id", "tool", "subject", "status",
        "exit_code", "authority_status", "coverage", "cursor", "context",
        "findings", "advisories", "warnings", "errors",
    ],
    "properties": {
        "schema_version": {"type": "string", "enum": [TABLE_EVALUATION_SCHEMA_VERSION]},
        "evaluation_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "tool": {"type": "object"},
        "subject": {"type": "object"},
        "status": {"type": "string", "enum": [
            "checked_clean", "checked_with_advisories", "findings",
            "incomplete", "unsupported", "invalid", "internal_error",
        ]},
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
        "authority_status": {"type": "string", "enum": ["self_attested"]},
        "coverage": {"type": "object"},
        "cursor": {"type": "object"},
        "context": {"type": "object"},
        "findings": {"type": "array"},
        "advisories": {"type": "array"},
        "warnings": {"type": "array"},
        "errors": {"type": "array"},
    },
}


def _canonical_digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _request(query_type, params):
    return {"type": query_type, "params": params}


def _adapter_policy(adapter_id):
    for adapter in capabilities()["adapters"]:
        identity = "%s@%s" % (adapter["name"], adapter["version"])
        if identity == adapter_id:
            digest = "sha256:" + adapter["digest"]
            return identity, digest
    identity = adapter_id or "srdcheck-adapter/unknown"
    return identity, _canonical_digest({"adapter": identity})


def _evidence(verdict):
    refs = []
    catalog = {}
    for rule_id in verdict.get("rule_ids") or []:
        value = str(rule_id)
        if value and len(value) <= 256 and value not in refs:
            refs.append(value)
            catalog[value] = {"kind": "rule_id", "rule_id": value}
    for citation in verdict.get("citations") or []:
        if isinstance(citation, dict):
            value = "citation-" + _canonical_digest(citation).split(":", 1)[1][:40]
            if value not in refs:
                refs.append(value)
                catalog[value] = {"kind": "citation", "citation": citation}
    return refs, catalog


def _caller_context(context):
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise ValueError("table evaluation context must be an object")
    unknown = sorted(set(context) - set(CALLER_CONTEXT_SCHEMA["properties"]))
    if unknown:
        raise ValueError("unknown table evaluation context field(s): %s" %
                         ", ".join(unknown))
    session_id = context.get("session_id")
    if session_id is not None and (not isinstance(session_id, str)
                                   or not 1 <= len(session_id) <= 256):
        raise ValueError("context session_id must be a 1..256 character string")
    supplied_refs = context.get("entity_refs", [])
    if (not isinstance(supplied_refs, list)
            or any(not isinstance(item, str) or not 1 <= len(item) <= 256
                   for item in supplied_refs)):
        raise ValueError("context entity_refs must contain 1..256 character strings")
    correlation_id = context.get("correlation_id")
    if correlation_id is not None and (
            not isinstance(correlation_id, str)
            or not 1 <= len(correlation_id) <= 244):
        raise ValueError("context correlation_id must be a 1..244 character string")
    refs = []
    for value in supplied_refs + (["correlation:" + correlation_id]
                                  if correlation_id is not None else []):
        if value not in refs:
            refs.append(value)
    return session_id, refs


def _coverage(status, evaluator_id, errors):
    complete = status in {"checked_clean", "checked_with_advisories", "findings"}
    if complete:
        compatible = eligible = evaluated = 1
        evaluator_status, skipped, reasons = "evaluated", 0, []
    elif status in {"unsupported", "invalid"}:
        compatible = eligible = evaluated = skipped = 0
        evaluator_status, reasons = "not_applicable", []
    else:
        compatible = eligible = 1
        evaluated, skipped = 0, 1
        evaluator_status, reasons = "skipped", list(errors)
    return {
        "complete": complete, "evidence_required": True,
        "input": 1, "compatible": compatible, "eligible": eligible,
        "evaluated": evaluated, "skipped": skipped,
        "evaluators": [{
            "id": evaluator_id, "required": True,
            "status": evaluator_status, "eligible": eligible,
            "evaluated": evaluated, "skipped": skipped,
            "skip_reasons": reasons,
        }],
    }


def _diagnostic(verdict, refs):
    data = verdict.get("data") if isinstance(verdict.get("data"), dict) else {}
    reason = data.get("reason_code") or "cannot-adjudicate"
    result = {
        "code": ("srdcheck." + str(reason).replace("-", "_"))[:256],
        "message": str(verdict.get("why") or "srdcheck could not adjudicate"),
    }
    missing = data.get("missing_inputs")
    if isinstance(missing, list) and missing and isinstance(missing[0], str):
        result["pointer"] = missing[0]
    if refs:
        result["evidence_refs"] = refs
    return result


def _table_advisories(verdict):
    decision = verdict.get("table_decision")
    if not isinstance(decision, dict):
        return []
    return [{
        "code": "srdcheck.table_ruling",
        "message": str(decision.get("outcome") or "A table ruling applies."),
        "authority": "table-ruling",
        "policy_id": decision.get("policy_id"),
        "scope": decision.get("scope"),
        "visibility": decision.get("visibility", "table"),
        "reversible": decision.get("reversible", True),
        "lineage": decision.get("lineage"),
    }]


def project_table_evaluation(verdict, query_type, params, context=None):
    """Return a deterministic, self-attested shared evaluation envelope."""
    if not isinstance(verdict, dict):
        verdict = verdict.as_dict()
    evaluator_id = (query_type if isinstance(query_type, str) and query_type
                    else "invalid-query")[:256]
    request = _request(query_type, params)
    input_digest = _canonical_digest(request)
    scope_name = query_type if isinstance(query_type, str) and query_type else "invalid-query"
    scope_ref = "srdcheck-query-scope:" + scope_name
    if len(scope_ref) > 256:
        scope_ref = "srdcheck-query-scope:" + _canonical_digest(scope_name).split(":", 1)[1]
    subject_id = "rules-query:" + scope_name + ":" + input_digest.split(":", 1)[1][:40]
    if len(subject_id) > 256:
        subject_id = "rules-query:" + input_digest.split(":", 1)[1]
    session_id, entity_refs = _caller_context(context)
    entity_refs = [scope_ref] + [ref for ref in entity_refs if ref != scope_ref]
    policy_version, policy_digest = _adapter_policy(verdict.get("adapter"))
    refs, evidence = _evidence(verdict)
    native_exit = verdict.get("exit_code")
    native_name = verdict.get("verdict")
    errors = []
    findings = []

    advisories = _table_advisories(verdict)
    if native_exit == 0 and native_name == "legal":
        status = "checked_with_advisories" if advisories else "checked_clean"
        exit_code, complete = 0, True
    elif native_exit == 1 and native_name == "illegal":
        if refs:
            status, exit_code, complete = "findings", 1, True
            material = {"request": request, "verdict": verdict}
            findings.append({
                "finding_id": "srdcheck-" + _canonical_digest(
                    material).split(":", 1)[1][:40],
                "code": "srdcheck.illegal",
                "severity": "finding",
                "summary": str(verdict.get("why") or
                               "proposal conflicts with the checked rule scope"),
                "evidence_refs": refs,
                "effective_policy": {
                    "adapter": verdict.get("adapter"),
                    "query_type": query_type,
                    "rule_ids": list(verdict.get("rule_ids") or []),
                    "citations": list(verdict.get("citations") or []),
                    "evidence": evidence,
                    "scope": {"kind": "rules_query", "query_type": scope_name,
                              "input_digest": input_digest},
                    "authority_boundary": "advisory rules verdict",
                },
                "policy_version": policy_version,
                "policy_digest": policy_digest,
            })
        else:
            status, exit_code, complete = "internal_error", 2, False
            errors.append({
                "code": "table_evaluation.finding_evidence_missing",
                "message": "an illegal verdict lacked rule or citation evidence",
            })
    elif native_exit == 2 and native_name == "cannot-adjudicate":
        reason = (verdict.get("data") or {}).get("reason_code")
        if reason == "invalid-input":
            status = "invalid"
        elif reason in {"unsupported-content", "unmodeled-rule"}:
            status = "unsupported"
        else:
            status = "incomplete"
        exit_code, complete = 2, False
        errors.append(_diagnostic(verdict, refs))
    else:
        status, exit_code, complete = "internal_error", 2, False
        errors.append({
            "code": "table_evaluation.native_verdict_invalid",
            "message": "srdcheck returned an incoherent native verdict",
        })

    evaluation_material = {
        "tool": "srdcheck", "version": __version__, "request": request,
        "native_verdict": verdict, "session_id": session_id,
        "entity_refs": entity_refs,
    }
    return {
        "schema_version": TABLE_EVALUATION_SCHEMA_VERSION,
        "evaluation_id": "srdcheck-" + _canonical_digest(
            evaluation_material).split(":", 1)[1][:40],
        "tool": {"name": "srdcheck", "version": __version__},
        "subject": {"kind": "rules_query", "id": subject_id,
                    "session_id": session_id, "entity_refs": entity_refs},
        "status": status,
        "exit_code": exit_code,
        "authority_status": "self_attested",
        "coverage": _coverage(status, evaluator_id, errors),
        "cursor": {"checked_through_event_id": None,
                   "gap_state": "none" if complete else "unknown",
                   "input_digest": input_digest},
        "context": {"roster_digest": None,
                    "policy_digest": policy_digest,
                    "config_digest": None,
                    "source_set_digest": policy_digest,
                    "session_descriptor_digest": None},
        "findings": findings,
        "advisories": advisories,
        "warnings": [],
        "errors": errors,
    }
