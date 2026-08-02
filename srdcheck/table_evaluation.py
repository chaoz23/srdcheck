"""Project one srdcheck verdict into ``table.evaluation/1.0``.

The shared envelope remains self-attested and advisory.  It does not turn a
rules verdict into table, encounter-state, or action-execution authority.
"""

import hashlib
import json

from . import __version__
from .access import capabilities


TABLE_EVALUATION_SCHEMA_VERSION = "table.evaluation/1.0"


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


def _evidence_refs(verdict):
    refs = []
    for rule_id in verdict.get("rule_ids") or []:
        value = str(rule_id)
        if value and len(value) <= 256 and value not in refs:
            refs.append(value)
    for citation in verdict.get("citations") or []:
        if isinstance(citation, dict):
            value = "citation-" + _canonical_digest(citation).split(":", 1)[1][:40]
            if value not in refs:
                refs.append(value)
    return refs


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


def project_table_evaluation(verdict, query_type, params):
    """Return a deterministic, self-attested shared evaluation envelope."""
    if not isinstance(verdict, dict):
        verdict = verdict.as_dict()
    evaluator_id = (query_type if isinstance(query_type, str) and query_type
                    else "invalid-query")[:256]
    request = _request(query_type, params)
    input_digest = _canonical_digest(request)
    subject_id = "rules-query-" + input_digest.split(":", 1)[1][:40]
    policy_version, policy_digest = _adapter_policy(verdict.get("adapter"))
    refs = _evidence_refs(verdict)
    native_exit = verdict.get("exit_code")
    native_name = verdict.get("verdict")
    errors = []
    findings = []

    if native_exit == 0 and native_name == "legal":
        status, exit_code, complete = "checked_clean", 0, True
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

    evaluated = 1 if complete else 0
    evaluator_status = "evaluated" if complete else "skipped"
    evaluator_reasons = [] if complete else list(errors)
    evaluation_material = {
        "tool": "srdcheck", "version": __version__, "request": request,
        "native_verdict": verdict,
    }
    return {
        "schema_version": TABLE_EVALUATION_SCHEMA_VERSION,
        "evaluation_id": "srdcheck-" + _canonical_digest(
            evaluation_material).split(":", 1)[1][:40],
        "tool": {"name": "srdcheck", "version": __version__},
        "subject": {"kind": "rules_query", "id": subject_id,
                    "session_id": None, "entity_refs": []},
        "status": status,
        "exit_code": exit_code,
        "authority_status": "self_attested",
        "coverage": {
            "complete": complete, "evidence_required": True,
            "input": 1, "compatible": 1, "eligible": 1,
            "evaluated": evaluated, "skipped": 1 - evaluated,
            "evaluators": [{
                "id": evaluator_id, "required": True,
                "status": evaluator_status, "eligible": 1,
                "evaluated": evaluated, "skipped": 1 - evaluated,
                "skip_reasons": evaluator_reasons,
            }],
        },
        "cursor": {"checked_through_event_id": None,
                   "gap_state": "none" if complete else "unknown",
                   "input_digest": input_digest},
        "context": {"roster_digest": None,
                    "policy_digest": policy_digest,
                    "config_digest": None,
                    "source_set_digest": policy_digest,
                    "session_descriptor_digest": None},
        "findings": findings,
        "advisories": [],
        "warnings": [],
        "errors": errors,
    }
