"""Lineage stamping and replay verification (T14). Content-neutral.

A state object is valid only as the output of a stamped transition chain:
each stamped state carries the hash of its predecessor, the declared event
that caused it, the rule ids that justified it, and whether the transition
was rule-derived or a ruling. verify() replays a chain and detects tampering.
"""

import hashlib
import json

LINEAGE_KEY = "lineage"


def canon_hash(state):
    body = {k: v for k, v in state.items() if k != LINEAGE_KEY}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def stamp(prev_state, event, verdict, next_state, kind="rule"):
    seq = prev_state.get(LINEAGE_KEY, {}).get("seq", 0) + 1
    out = dict(next_state)
    out[LINEAGE_KEY] = {
        "seq": seq,
        "prev": canon_hash(prev_state),
        "event": event,
        "rule_ids": list(verdict.rule_ids),
        "kind": kind,
        "self": None,
    }
    out[LINEAGE_KEY]["self"] = canon_hash(out)
    return out


def verify(initial_state, events, apply_fn):
    """Replay events from initial_state; return (ok, states). apply_fn is
    the reducer: fn(state, event) -> (verdict, next_state or None)."""
    state = initial_state
    states = [state]
    for ev in events:
        verdict, nxt = apply_fn(state, ev)
        if nxt is None:
            return False, states
        lin = nxt.get(LINEAGE_KEY, {})
        if lin.get("prev") != canon_hash(state):
            return False, states
        if lin.get("self") != canon_hash(nxt):
            return False, states
        state = nxt
        states.append(state)
    return True, states
