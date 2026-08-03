# Safe event and state transitions

SRDCheck is stateless. It evaluates a declared event and verifies a commit, but
the agent-DM, Discord host, VTT, or other caller owns the authoritative event
log and campaign state. The safe flow is a two-step compare-and-swap:

1. Read the host's current canonical state.
2. Call `event.apply` with that state, the declared event, and a stable
   `idempotency_key`.
3. Keep the exact `data.transition` proposal. It binds the event and key to
   `state_precondition_hash` and commits to the proposed state with
   `result_hash`.
4. Call `transition.commit` with the host's current state and that exact
   transition.
5. Only on exit code 0, atomically replace host state with `data.next_state`.

For Discord text today, use the message or gateway event snowflake as the
idempotency key. For future voice/video, use the host's durable utterance or
resolved-intent event ID—not an ASR transcript fragment, timestamp, or model
request ID that may change during retries.

```json
{
  "state": {"speed": 30, "conditions": [], "turn": {
    "action_spent": false, "bonus_action_spent": false,
    "reaction_spent": false, "free_interaction_spent": false,
    "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0
  }},
  "event": {"type": "move", "feet": 10},
  "idempotency_key": "discord-message-123456789"
}
```

`event.apply` is an evaluation and proposal, not permission to write blindly.
Its transition uses `srdcheck.transition/1.0` and includes:

- `idempotency_key`: stable host event identity, or a deterministic `auto:` key
  when omitted;
- `transition_id`: SHA-256 identity over adapter, event, key, and precondition;
- `state_precondition_hash`: full SHA-256 of the evaluated state;
- `result_hash`: full SHA-256 of the proposed stamped next state; and
- the exact normalized event.

The agent-facing table-evaluation projection also places the precondition hash
in `cursor.state_precondition_hash` whenever the query has a state object.

## Retry, conflict, and reconciliation

- **Retry before persistence:** call `transition.commit` again with the same
  current state and exact proposal. The semantic commit receipt is identical.
- **Retry after persistence:** call it with the already committed next state.
  Bound lineage proves the same event/key/transition and returns the same
  `next_state`, transition, and verified caller-owned-persistence receipt
  without applying the event twice.
- **Concurrent proposals:** only the proposal whose precondition matches the
  authoritative state may commit. A later proposal from that old state returns
  exit code 2, `reason_code: stale-state`, `recoverability: conflict`, and
  `suggested_next_action: reconcile-state`.
- **Out-of-order Discord or agent events:** order them using the host's durable
  event log, then call `event.apply` again against the resulting current state
  using the original host event ID. Never edit the stale proposal or patch its
  hashes.
- **Tampering or corruption:** a transition that cannot be reproduced exactly
  returns `invalid-input`; do not persist any state.

`transition.commit` cannot make a multi-process write atomic by itself. The
host must use its database/version compare-and-swap, transaction, or single
authoritative event-loop primitive around the final replacement. This design
keeps SRDCheck deterministic and local while making the integration boundary
explicit and testable.
