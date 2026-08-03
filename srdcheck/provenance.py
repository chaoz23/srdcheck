"""Content-neutral fact and authority provenance for adjudication receipts."""

from copy import deepcopy
import json


SOURCE_KINDS = (
    "caller", "dm", "player", "agent", "transcript", "sensor",
    "imported-state", "system",
)
DECISION_KINDS = ("ruling", "override")
DECISION_SCOPES = ("once", "encounter", "session", "campaign")

SOURCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind"],
    "properties": {
        "kind": {"type": "string", "enum": list(SOURCE_KINDS)},
        "id": {"type": "string", "minLength": 1, "maxLength": 256},
    },
}

ASSERTED_FACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "source", "confidence"],
    "properties": {
        "path": {"type": "string", "pattern": r"^/"},
        "source": SOURCE_SCHEMA,
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

ASSERTED_FACTS_SCHEMA = {
    "type": "array",
    "items": ASSERTED_FACT_SCHEMA,
}

TABLE_DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "outcome", "origin", "scope"],
    "properties": {
        "kind": {"type": "string", "enum": list(DECISION_KINDS)},
        "outcome": {"type": "string", "minLength": 1, "maxLength": 1024},
        "origin": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"type": "string", "enum": ["dm"]},
                "id": {"type": "string", "minLength": 1, "maxLength": 256},
            },
        },
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"type": "string", "enum": list(DECISION_SCOPES)},
                "id": {"type": "string", "minLength": 1, "maxLength": 256},
            },
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 2048},
        "visibility": {"type": "string", "enum": ["dm-only", "table"]},
        "reversible": {"type": "boolean"},
        "policy_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "lineage": {
            "type": "object",
            "additionalProperties": False,
            "required": ["authority", "affected_query", "affected_rule_ids",
                         "source_rule_unchanged"],
            "properties": {
                "authority": {"type": "string", "enum": ["table-ruling"]},
                "affected_query": {"type": "string", "minLength": 1},
                "affected_rule_ids": {
                    "type": "array", "items": {"type": "string"}},
                "source_rule_unchanged": {"type": "boolean", "enum": [True]},
            },
        },
    },
}

FACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "value", "source", "confidence"],
    "properties": {
        "path": {"type": "string"},
        "value": {},
        "source": SOURCE_SCHEMA,
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
    },
}

FACT_TRACE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["asserted", "consumed", "derived", "missing"],
    "properties": {
        "asserted": {"type": "array", "items": FACT_SCHEMA},
        "consumed": {"type": "array", "items": {"type": "string"}},
        "derived": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "value", "basis"],
                "properties": {
                    "path": {"type": "string"},
                    "value": {},
                    "basis": {"type": "string", "enum": ["rule_result"]},
                },
            },
        },
        "missing": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path"],
                "properties": {"path": {"type": "string", "minLength": 1}},
            },
        },
    },
}

RULE_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["authority", "verdict", "exit_code", "why", "adapter",
                 "rule_ids", "citations"],
    "properties": {
        "authority": {"type": "string", "enum": ["rules-advisory"]},
        "verdict": {"type": "string"},
        "exit_code": {"type": "integer"},
        "why": {"type": "string"},
        "adapter": {"type": "string"},
        "rule_ids": {"type": "array", "items": {"type": "string"}},
        "citations": {"type": "array"},
    },
}

STATE_MUTATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "operations"],
    "properties": {
        "status": {"type": "string", "enum": ["none", "proposed"]},
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["op", "path", "value"],
                "properties": {
                    "op": {"type": "string", "enum": ["replace"]},
                    "path": {"type": "string", "enum": ["/"]},
                    "value": {},
                },
            },
        },
    },
}

EXPLANATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rule", "situation_facts", "table_decision", "state_mutation"],
    "properties": {
        "rule": {"type": "string"},
        "situation_facts": {"type": "array", "items": {"type": "string"}},
        "table_decision": {"type": "string"},
        "state_mutation": {"type": "string"},
    },
}


def annotate_params(params, asserted_facts=None):
    """Return every request leaf as an assertion with optional caller metadata.

    ``consumed`` means the normalized fact was validated and supplied to the
    selected rules handler. It deliberately does not claim causal influence.
    """
    annotations = {}
    for item in asserted_facts or []:
        path = item["path"]
        if path in annotations:
            raise ValueError(f"duplicate asserted fact path: {path}")
        annotations[path] = item
    leaves = dict(_leaves(params))
    unknown = sorted(set(annotations) - set(leaves))
    if unknown:
        raise ValueError("asserted fact path(s) not present in params: " +
                         ", ".join(unknown))
    facts = []
    for path, value in leaves.items():
        metadata = annotations.get(path)
        facts.append({
            "path": path,
            "value": deepcopy(value),
            "source": deepcopy(metadata["source"] if metadata else
                               {"kind": "caller"}),
            "confidence": metadata["confidence"] if metadata else None,
        })
    return facts


def derived_facts(data, *, asserted=()):
    ignored = {"reason_code", "recoverability", "missing_inputs",
               "suggested_next_action", "required_authority",
               "validation_errors", "unknown_fields", "next_state"}
    asserted_values = {
        ("/data" + fact["path"], _canonical_value(fact["value"]))
        for fact in asserted
    }
    return [{"path": "/data" + path, "value": deepcopy(value),
             "basis": "rule_result"}
            for path, value in _leaves(data or {})
            if path.lstrip("/").split("/", 1)[0] not in ignored
            if ("/data" + path, _canonical_value(value)) not in asserted_values]


def missing_facts(data):
    values = (data or {}).get("missing_inputs", [])
    return [{"path": value} for value in values if isinstance(value, str)]


def state_mutation(data):
    next_state = (data or {}).get("next_state")
    if isinstance(next_state, dict):
        return {"status": "proposed", "operations": [{
            "op": "replace", "path": "/", "value": deepcopy(next_state),
        }]}
    return {"status": "none", "operations": []}


def human_explanation(why, facts, table_decision, mutation):
    situation = [
        f"{fact['path']} = {json.dumps(fact['value'], ensure_ascii=False)} "
        f"(source: {fact['source']['kind']}; confidence: "
        f"{fact['confidence'] if fact['confidence'] is not None else 'unknown'})"
        for fact in facts
    ]
    if table_decision is None:
        decision = ("No DM/table decision was recorded; the rules result remains "
                    "advisory.")
    else:
        decision = (f"DM {table_decision['kind']} for "
                    f"{table_decision['scope']['kind']} scope: "
                    f"{table_decision['outcome']}")
    mutation_text = ("A replacement state was proposed but not persisted."
                     if mutation["status"] == "proposed" else
                     "No state mutation was performed.")
    return {
        "rule": why,
        "situation_facts": situation,
        "table_decision": decision,
        "state_mutation": mutation_text,
    }


def _leaves(value, path=""):
    stack = [(path, value)]
    while stack:
        current_path, current = stack.pop()
        if isinstance(current, dict):
            for key in reversed(sorted(current)):
                token = str(key).replace("~", "~0").replace("/", "~1")
                stack.append((current_path + "/" + token, current[key]))
        elif isinstance(current, list):
            for index in range(len(current) - 1, -1, -1):
                stack.append((current_path + "/" + str(index), current[index]))
        else:
            yield current_path or "/", current


def _canonical_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
