# Fact, rule, and DM-decision provenance

Verdict schema 4.0 prevents a caller assertion—especially an ASR, transcript,
vision, or agent inference—from looking like an SRD-derived fact or a DM ruling.
It adds no MCP tool and does not make SRDCheck stateful.

## Request metadata

`asserted_facts` annotates leaves already present in `params`; it does not carry
a second copy of their values. Every entry requires:

- `path`: JSON Pointer into `params`;
- `source`: a `kind` and optional stable `id`;
- `confidence`: a finite number from 0 through 1.

Supported source kinds are `caller`, `dm`, `player`, `agent`, `transcript`,
`sensor`, `imported-state`, and `system`. An annotation for a nonexistent path,
a duplicate path, or invalid metadata returns `invalid-input` before dispatch.
Legacy unannotated parameter leaves are still visible as source `caller` with
unknown confidence.

An optional `table_decision` records a `ruling` or `override`, its text outcome,
DM origin, and once/encounter/session/campaign scope. The calling agent may
be that DM: use `origin.kind: "dm"` and identify the agent in `origin.id`.

```json
{
  "type": "reaction.available",
  "params": {"spent_since_turn_start": false},
  "asserted_facts": [{
    "path": "/spent_since_turn_start",
    "source": {"kind": "agent", "id": "discord-ai-dm"},
    "confidence": 0.93
  }],
  "table_decision": {
    "kind": "override",
    "outcome": "Unavailable because of the scene's time-stop effect.",
    "origin": {"kind": "dm", "id": "discord-ai-dm"},
    "scope": {"kind": "session", "id": "session-7"}
  }
}
```

Use that envelope with `--pipe`; direct `query` also accepts
`--asserted-facts` and `--table-decision` JSON. Every specialized MCP tool
publishes the same optional metadata alongside its mechanic arguments. The
`table_evaluation` tool accepts the metadata beside `query_type` and `params`.

## Receipt semantics

- `facts.asserted` contains the request facts and their origin/confidence.
- `facts.consumed` contains paths actually supplied to the rules handler. It is
  empty when validation stops the request before dispatch.
- `facts.derived` contains structured data derived by the handler and names
  `rule_result` as its basis. Echoed input fields are not mislabeled derived.
- `facts.missing` is machine-recoverable missing input, separate from the
  human-readable `assumptions` boundary.
- `rule_result` repeats the native verdict as explicitly `rules-advisory`.
- `table_decision` is the recorded DM ruling or `null`; it never changes
  `rule_result`.
- `state_mutation` is `none` for ordinary adjudication. `event.apply` reports
  its returned `next_state` as a `proposed` root replacement; SRDCheck does not
  persist it. Transition protection is a separate contract.
- `explanation` renders rule text, situation facts, DM decision, and mutation
  status as distinct human-readable sections.

This separation is a receipt, not authority escalation. Persistence and policy
precedence are defined in [table policies](table-policies.md);
stale-state/idempotency belongs to
the transition contract.
