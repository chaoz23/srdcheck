# Machine-actionable refusal recovery

`cannot-adjudicate` is a scoped result, not a transport failure. It preserves
exit code `2` while explaining, in stable machine fields, what prevented the
named check and what the caller can do next. JSON-RPC errors remain reserved
for malformed protocol or transport requests.

The current vocabulary is refusal contract 1.1. It adds `stale-state`,
`conflict`, and `reconcile-state`; every 1.0 mapping keeps its original
meaning.

Verdict schema v4 keeps refusal control
flow inside the existing `data` object:

```json
{
  "verdict": "cannot-adjudicate",
  "exit_code": 2,
  "why": "Explanatory prose for a person.",
  "citations": [],
  "rule_ids": [],
  "adapter": "srd-5.2.1@0.2.1",
  "coverage_level": "rule-surface-complete",
  "checked_scope": ["listed uses and prohibitions"],
  "unchecked_scope": ["fine-manipulation ambiguity", "narrative consequences"],
  "assumptions": ["the supplied use kind describes the proposal"],
  "data": {
    "reason_code": "gm-discretion",
    "recoverability": "authority",
    "missing_inputs": [],
    "suggested_next_action": "resolve-table-ruling",
    "required_authority": "dm"
  }
}
```

Consumers must branch on these fields rather than parsing `why`. The `why`
string remains non-contractual explanatory prose.

## Stable classes and recovery actions

| `reason_code` | Meaning | `recoverability` | Default `suggested_next_action` | Authority |
|---|---|---|---|---|
| `invalid-input` | A supplied value or request shape is invalid. | `retry` | `repair-request` | — |
| `missing-fact` | The named check needs one or more facts the caller did not supply. | `retry` | `provide-facts` | — |
| `unsupported-content` | The content is not carried by the selected adapter. | `alternate-path` | `select-adapter` | — |
| `unmodeled-rule` | The content may be known, but this capability does not model the requested rule. | `alternate-path` | `use-other-capability` | — |
| `rules-ambiguous` | The rules text does not determine one answer. | `authority` | `resolve-table-ruling` | `dm` |
| `gm-discretion` | The rules deliberately leave the decision to table authority. | `authority` | `resolve-table-ruling` | `dm` |
| `stale-state` | Authoritative state no longer matches the evaluated transition precondition. | `conflict` | `reconcile-state` | — |

`missing_inputs` is always an array of request-relative machine paths, using
dotted object keys and bracketed array indexes. It is empty when no additional
fact can repair the request. A capability may return
`use-other-capability` for known content sent to the wrong capability instead
of the usual `unsupported-content` default. When an authorized direct decision
or matching table policy is already attached to an authority-bound refusal,
`apply-table-decision` replaces `resolve-table-ruling`; the advisory rules
refusal remains intact and the caller does not prompt the DM again.

`recoverability` has five stable values:

- `retry`: repair this request or provide its missing facts, then retry it;
- `alternate-path`: select another adapter or capability;
- `authority`: resolve the question through the named table authority; and
- `conflict`: reconcile caller-owned state/event order and re-evaluate; and
- `terminal`: no machine recovery is known, so stop.

`stop` and `terminal` are the conservative fallback only for a legacy or
third-party refusal that does not provide a first-party classification. Shipped
first-party refusals use one of the seven classes above and a more specific
recovery path.

## Consumer algorithm

1. Treat exit codes `0` and `1` as scoped adjudication results.
2. On exit code `2`, read `data.reason_code`, `data.recoverability`,
   `data.missing_inputs`, and `data.suggested_next_action`.
3. For `repair-request` or `provide-facts`, fix the named paths and retry the
   same capability.
4. For `select-adapter` or `use-other-capability`, discover the advertised
   machine surface and choose an applicable path; do not retry unchanged.
5. For `resolve-table-ruling`, check `required_authority`. If the calling agent
   is the authorized DM, it may rule directly. Otherwise, route the question to
   whoever holds DM authority.
6. For `apply-table-decision`, consume the attached `table_decision`; do not
   prompt DM authority again.
7. For `reconcile-state`, order the host's durable events and evaluate the
   event again against authoritative current state. Never patch or force-apply
   the stale proposal; see [safe state transitions](state-transitions.md).
8. Record the resulting authority decision as a **table ruling**, never as an
   SRD-derived srdcheck result.
9. For the legacy `stop` fallback, do not infer recovery from `why`.

This is intentionally role-neutral. “DM authority” describes permission, not a
separate human. The primary caller may be an AI agent running the game.

## Examples by reason class

```json
{"reason_code":"invalid-input","recoverability":"retry","missing_inputs":[],"suggested_next_action":"repair-request"}
{"reason_code":"missing-fact","recoverability":"retry","missing_inputs":["leaves_reach"],"suggested_next_action":"provide-facts"}
{"reason_code":"unsupported-content","recoverability":"alternate-path","missing_inputs":[],"suggested_next_action":"select-adapter"}
{"reason_code":"unmodeled-rule","recoverability":"alternate-path","missing_inputs":[],"suggested_next_action":"use-other-capability"}
{"reason_code":"rules-ambiguous","recoverability":"authority","missing_inputs":[],"suggested_next_action":"resolve-table-ruling","required_authority":"dm"}
{"reason_code":"gm-discretion","recoverability":"authority","missing_inputs":[],"suggested_next_action":"resolve-table-ruling","required_authority":"dm"}
{"reason_code":"gm-discretion","recoverability":"authority","missing_inputs":[],"suggested_next_action":"apply-table-decision","required_authority":"dm"}
{"reason_code":"stale-state","recoverability":"conflict","missing_inputs":[],"suggested_next_action":"reconcile-state"}
```

The complete vocabulary and canonical mappings are also published by
`srdcheck capabilities`; clients should use its versioned refusal contract for
discovery.
