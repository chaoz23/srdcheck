# Privacy-safe observability

SRDCheck's verdict path remains deterministic and offline. Operational timing
and request occurrence data use a separate, opt-in
`srdcheck.observability/1.0` event contract. Those fields never enter the
verdict envelope, its deterministic identity, or table state.

This boundary is designed for the primary integration persona: an agent acting
as the DM in a real Discord table. The Discord host should supply the message or
resolved-intent event snowflake as `request_id`. That joins a rules check to
delivery and feedback without logging message text.

## Enable tracing

CLI events are canonical NDJSON on stderr; the verdict remains the only stdout
payload:

```bash
python -m srdcheck query mage-hand.use '{"kind":"attack"}' \
  --trace --request-id 123456789012345678
```

For the stdio MCP process, set `SRDCHECK_TRACE=stderr`. MCP tool inputs accept
the same optional `request_id`. `SRDCHECK_TRACE=off` (the default) emits
nothing. Any other setting fails closed instead of enabling an undocumented
logging mode.

Library hosts can pass a callable sink to `observe_query`. It returns the
original verdict plus a separate trace summary:

```python
from srdcheck import observe_query

observed = observe_query(
    engine, "mage-hand.use", {"kind": "attack"},
    request_id="123456789012345678", sink=events.append,
)
verdict = observed.verdict
```

If the caller omits `request_id`, SRDCheck derives a stable SHA-256 identity
from the canonical structured request. That fallback is useful for replay and
tests; a delivery-layer event ID is preferable when identical requests are
distinct table occurrences.

## Event contract

Every observed query emits `request.started`, then exactly one of
`request.completed`, `request.refused`, or `request.error`. Events contain only:

- request and deterministic verdict identities;
- query type, exit code, and refusal reason class;
- validation accepted/rejected status;
- engine and loaded adapter/data/rules versions;
- elapsed milliseconds; and
- a sanitized exception class for internal errors.

The event schema is published by `srdcheck capabilities` under
`observability_contract`. `verdict_id` hashes the complete deterministic native
verdict. Timing never changes that identity.

## Redaction and residual privacy risk

Events exclude parameters, raw player or campaign content, `why`, citations,
source text, table decisions, state, and exception messages. Tests seed those
classes of private material and fail if they reach the event stream.

Metadata is not anonymous. A caller-owned request ID can be linkable to a
Discord message, query types reveal which capability was invoked, and timing is
behavioral data. Treat the stream as private operational telemetry:

- do not make it visible to players by default;
- restrict access to the table owner/operator;
- use the shortest retention that answers the pilot question (seven days is a
  reasonable starting point, not a product default);
- document export and deletion with the host's Discord data controls; and
- aggregate refusal and latency counts only after removing request IDs.

SRDCheck itself persists no events and supplies no network exporter. Local and
hosted deployments own their sink, access controls, retention, export, and
deletion. Disabling or losing the sink never changes a verdict.
