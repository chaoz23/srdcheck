"""Deterministic, caller-persisted transition commit contracts.

SRDCheck owns no mutable state.  This module binds a proposed transition to
the exact state it was evaluated against so a host can perform an atomic
compare-and-swap instead of applying a stale Discord or agent event.
"""

import hashlib
import json
from copy import deepcopy


TRANSITION_SCHEMA_VERSION = "srdcheck.transition/1.0"
_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"

TRANSITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "adapter", "idempotency_key", "transition_id",
        "state_precondition_hash", "event", "result_hash",
    ],
    "properties": {
        "schema_version": {
            "type": "string", "enum": [TRANSITION_SCHEMA_VERSION],
        },
        "adapter": {"type": "string", "minLength": 1, "maxLength": 256},
        "idempotency_key": {
            "type": "string", "minLength": 1, "maxLength": 256,
        },
        "transition_id": {"type": "string", "pattern": _HASH_PATTERN},
        "state_precondition_hash": {
            "type": "string", "pattern": _HASH_PATTERN,
        },
        "event": {"type": "object"},
        "result_hash": {"type": "string", "pattern": _HASH_PATTERN},
    },
}


def canonical_hash(value):
    """Return a full SHA-256 commitment to one finite JSON value."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def identity(adapter_id, state, event, idempotency_key=None):
    """Return the stable key and identity for a state-bound event proposal."""
    precondition = canonical_hash(state)
    if idempotency_key is None:
        idempotency_key = "auto:" + canonical_hash({
            "adapter": adapter_id,
            "state_precondition_hash": precondition,
            "event": event,
        }).split(":", 1)[1]
    material = {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "adapter": adapter_id,
        "idempotency_key": idempotency_key,
        "state_precondition_hash": precondition,
        "event": event,
    }
    return idempotency_key, precondition, canonical_hash(material)


def proposal(adapter_id, state, event, next_state, idempotency_key=None):
    """Describe a deterministic successor without persisting it."""
    key, precondition, transition_id = identity(
        adapter_id, state, event, idempotency_key)
    return {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "adapter": adapter_id,
        "idempotency_key": key,
        "transition_id": transition_id,
        "state_precondition_hash": precondition,
        "event": deepcopy(event),
        "result_hash": canonical_hash(next_state),
    }


def commit_receipt(transition):
    """Return the same semantic receipt for a first commit and every retry."""
    material = {
        "schema_version": transition["schema_version"],
        "transition_id": transition["transition_id"],
        "idempotency_key": transition["idempotency_key"],
        "state_precondition_hash": transition["state_precondition_hash"],
        "result_hash": transition["result_hash"],
        "status": "verified",
        "persistence": "caller-owned",
    }
    return {**material, "receipt_hash": canonical_hash(material)}
