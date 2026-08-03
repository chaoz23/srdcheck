# Persistent DM rulings and table policies

SRDCheck is stateless: the DM or host owns a portable
`srdcheck.table-policy/1.0` manifest and supplies it with each relevant query.
This is also the primary agent-as-DM workflow. The agent can reuse an already
authorized ruling without asking itself—or a human DM—the same question on
every turn. SRDCheck applies policy deterministically but never writes a
campaign file, changes the SRD result, or grants DM authority to the caller.

The canonical [example manifest](example-table-policy.json) is ordinary,
diff-friendly JSON. Each policy records:

- stable policy ID and DM author;
- reason and `ruling` or `override` outcome;
- affected query type and optional JSON-Pointer/value matches into `params`;
- `once`, `encounter`, `session`, or `campaign` scope with a stable ID;
- `dm-only` or `table` visibility; and
- whether the decision is reversible.

`enabled: false` preserves a reversed policy's history while preventing it from
matching. A host may instead remove it. Visibility is policy metadata, not an
access-control system: a Discord or voice/video host must redact `dm-only`
content before sending a receipt to players.

## Match and precedence

Supply scope IDs separately as `policy_context`. A `once` policy matches
`request_id`, making retries and replay deterministic; encounter, session, and
campaign policies match their corresponding IDs. A missing or different ID
does not match.

Query `match` keys are JSON Pointers into the query's `params`. An empty object
matches every valid invocation of that query type. When several scopes match,
the most specific wins:

`once > encounter > session > campaign`

Two matching policies at the same specificity are ambiguous and return
`cannot-adjudicate`/`invalid-input`; SRDCheck will not silently choose between
conflicting DM instructions. An explicit `table_decision` and a manifest are
also mutually exclusive in one request.

## Agent and CLI usage

Python:

```python
result = adapter.query(
    "reaction.available",
    {"spent_since_turn_start": False},
    table_policy=manifest,
    policy_context={"campaign_id": "campaign-7"},
)
```

Pipe, specialized MCP tools, and `table_evaluation` accept the same
`table_policy` and `policy_context` fields. Direct CLI queries use
`--table-policy '<json>' --policy-context '<json>'`. These are optional fields
on existing MCP tools, so persistent rulings add no discovery burden.

Import/validate and canonical export a file with:

```console
srdcheck policy validate docs/example-table-policy.json
srdcheck policy export docs/example-table-policy.json
```

The Python `import_manifest` and `export_manifest` functions provide the same
validated round trip. Canonical export is UTF-8 JSON with stable key ordering,
two-space indentation, and a trailing newline.

## Receipt authority

A matching decision appears separately from the unchanged
`rule_result`. Its lineage is explicitly `table-ruling`, names the affected
query and rule IDs, and states `source_rule_unchanged: true`. The native verdict
and exit code remain the advisory rules answer; consumers apply the authorized
table decision. An authority-bound refusal with a matching decision reports
`suggested_next_action: apply-table-decision`, not another DM prompt. The shared
`table.evaluation/1.0` projection carries the table
decision as an advisory and therefore reports `checked_with_advisories` when
the source-rule result is otherwise clean.
