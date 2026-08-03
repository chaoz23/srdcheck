"""Portable, caller-owned DM rulings and house-policy manifests.

SRDCheck deliberately does not persist table state.  A host imports a manifest,
supplies it with a query, and persists any later edits itself.  This keeps policy
application deterministic for local agents, Discord bots, and hosted services.
"""

from copy import deepcopy
import json

from .schema import issues as schema_issues


MANIFEST_SCHEMA_ID = "srdcheck.table-policy/1.0"
SCOPE_KINDS = ("once", "encounter", "session", "campaign")
SCOPE_CONTEXT_KEYS = {
    "once": "request_id",
    "encounter": "encounter_id",
    "session": "session_id",
    "campaign": "campaign_id",
}
_SCOPE_PRIORITY = {kind: len(SCOPE_KINDS) - index
                   for index, kind in enumerate(SCOPE_KINDS)}

POLICY_CONTEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        key: {"type": "string", "minLength": 1, "maxLength": 256}
        for key in SCOPE_CONTEXT_KEYS.values()
    },
}

POLICY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "author", "reason", "query", "decision", "scope",
                 "visibility", "reversible"],
    "properties": {
        "id": {"type": "string", "minLength": 1, "maxLength": 256},
        "enabled": {"type": "boolean"},
        "author": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"type": "string", "enum": ["dm"]},
                "id": {"type": "string", "minLength": 1,
                       "maxLength": 256},
            },
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 2048},
        "query": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "match"],
            "properties": {
                "type": {"type": "string", "minLength": 1,
                         "maxLength": 256},
                "match": {"type": "object", "additionalProperties": {}},
            },
        },
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "outcome"],
            "properties": {
                "kind": {"type": "string", "enum": ["ruling", "override"]},
                "outcome": {"type": "string", "minLength": 1,
                            "maxLength": 1024},
            },
        },
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "id"],
            "properties": {
                "kind": {"type": "string", "enum": list(SCOPE_KINDS)},
                "id": {"type": "string", "minLength": 1,
                       "maxLength": 256},
            },
        },
        "visibility": {"type": "string", "enum": ["dm-only", "table"]},
        "reversible": {"type": "boolean"},
    },
}

MANIFEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "policies"],
    "properties": {
        "schema": {"type": "string", "enum": [MANIFEST_SCHEMA_ID]},
        "table": {"type": "string", "minLength": 1, "maxLength": 256},
        "policies": {"type": "array", "items": POLICY_SCHEMA,
                     "maxItems": 1000},
    },
}


def import_manifest(value):
    """Validate and return an isolated manifest from JSON text or an object."""
    if isinstance(value, (str, bytes, bytearray)):
        value = json.loads(value)
    problems = schema_issues(value, MANIFEST_SCHEMA, path="$.table_policy")
    if problems:
        raise ValueError("invalid table-policy manifest: " +
                         "; ".join(str(problem) for problem in problems))
    ids = [policy["id"] for policy in value["policies"]]
    duplicates = sorted({policy_id for policy_id in ids
                         if ids.count(policy_id) > 1})
    if duplicates:
        raise ValueError("duplicate table-policy id(s): " +
                         ", ".join(duplicates))
    for policy in value["policies"]:
        for pointer in policy["query"]["match"]:
            if not _valid_pointer(pointer):
                raise ValueError(
                    f"policy {policy['id']!r} has invalid JSON Pointer "
                    f"match path: {pointer!r}")
    return deepcopy(value)


def export_manifest(value):
    """Return stable, diff-friendly JSON suitable for people and machines."""
    manifest = import_manifest(value)
    return json.dumps(manifest, ensure_ascii=False, indent=2,
                      sort_keys=True) + "\n"


def resolve_policy(query_type, params, manifest, context=None):
    """Return the single most-specific matching policy as a table decision.

    Same-scope conflicts fail closed.  Different scopes use the familiar
    once > encounter > session > campaign specificity order.
    """
    manifest = import_manifest(manifest)
    context = deepcopy(context or {})
    problems = schema_issues(context, POLICY_CONTEXT_SCHEMA,
                             path="$.policy_context")
    if problems:
        raise ValueError("invalid policy context: " +
                         "; ".join(str(problem) for problem in problems))
    candidates = []
    for policy in manifest["policies"]:
        if policy.get("enabled", True) is False:
            continue
        if policy["query"]["type"] != query_type:
            continue
        scope = policy["scope"]
        if context.get(SCOPE_CONTEXT_KEYS[scope["kind"]]) != scope["id"]:
            continue
        if not all(_pointer_value(params, pointer) == expected
                   for pointer, expected in policy["query"]["match"].items()):
            continue
        candidates.append(policy)
    if not candidates:
        return None
    priority = max(_SCOPE_PRIORITY[item["scope"]["kind"]]
                   for item in candidates)
    winners = [item for item in candidates
               if _SCOPE_PRIORITY[item["scope"]["kind"]] == priority]
    if len(winners) != 1:
        raise ValueError(
            "ambiguous matching table policies at the same scope: " +
            ", ".join(sorted(item["id"] for item in winners)))
    policy = winners[0]
    return {
        "kind": policy["decision"]["kind"],
        "outcome": policy["decision"]["outcome"],
        "origin": deepcopy(policy["author"]),
        "scope": deepcopy(policy["scope"]),
        "reason": policy["reason"],
        "visibility": policy["visibility"],
        "reversible": policy["reversible"],
        "policy_id": policy["id"],
    }


def attach_lineage(decision, query_type, rule_ids):
    """Label a decision as table authority without altering source-rule data."""
    if decision is None:
        return None
    value = deepcopy(decision)
    value.setdefault("visibility", "table")
    value.setdefault("reversible", True)
    value["lineage"] = {
        "authority": "table-ruling",
        "affected_query": query_type,
        "affected_rule_ids": list(rule_ids),
        "source_rule_unchanged": True,
    }
    return value


def _valid_pointer(pointer):
    if (not isinstance(pointer, str) or not pointer.startswith("/")
            or len(pointer) > 512):
        return False
    return all("~" not in token.replace("~0", "").replace("~1", "")
               for token in pointer.split("/")[1:])


def _pointer_value(value, pointer):
    current = value
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                if (not token.isascii() or not token.isdigit()
                        or (len(token) > 1 and token.startswith("0"))):
                    return _MISSING
                current = current[int(token)]
            else:
                current = current[token]
        except (KeyError, IndexError, TypeError, ValueError):
            return _MISSING
    return current


_MISSING = object()
