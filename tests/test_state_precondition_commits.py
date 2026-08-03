"""State-bound, idempotent transition commits for agent-DM hosts (#34)."""

import copy
import json
import pathlib

from srdcheck import load_adapter, project_table_evaluation
from srdcheck.engine import Engine
from srdcheck.transitions import TRANSITION_SCHEMA, canonical_hash


ADAPTER = load_adapter("srd-5.2.1")
ADAPTER_ROOT = (pathlib.Path(__file__).resolve().parents[1] / "srdcheck" /
                "adapters" / "srd-5.2.1")
ENGINE = Engine([ADAPTER_ROOT])


def state():
    return {
        "speed": 30,
        "conditions": [],
        "turn": {
            "action_spent": False,
            "bonus_action_spent": False,
            "reaction_spent": False,
            "free_interaction_spent": False,
            "movement_ft_spent": 0,
            "spell_slots_spent_this_turn": 0,
        },
        "dead": False,
        "stable": False,
        "death_save_successes": 0,
        "death_save_failures": 0,
    }


def propose(current, event, key):
    return ENGINE.query("event.apply", {
        "state": current, "event": event, "idempotency_key": key,
    })


def commit(current, transition):
    return ENGINE.query("transition.commit", {
        "state": current, "transition": transition,
    })


def test_runtime_and_published_transition_schemas_do_not_drift():
    published = json.loads(
        (ADAPTER_ROOT / "transition_schema.json").read_text())["schema"]
    assert published == TRANSITION_SCHEMA


def test_stateful_evaluation_exposes_exact_precondition_hash():
    current = state()
    params = {
        "state": current,
        "event": {"type": "move", "feet": 5},
        "idempotency_key": "discord-message-100",
    }
    verdict = ENGINE.query("event.apply", params)
    projected = project_table_evaluation(verdict, "event.apply", params)

    expected = canonical_hash(current)
    assert verdict.data["state_precondition_hash"] == expected
    assert verdict.data["transition"]["state_precondition_hash"] == expected
    assert projected["cursor"]["state_precondition_hash"] == expected


def test_proposals_and_result_hashes_are_deterministic_and_input_bound():
    current = state()
    event = {"type": "move", "feet": 5}
    first = propose(current, event, "discord-message-101")
    second = propose(copy.deepcopy(current), copy.deepcopy(event),
                     "discord-message-101")

    assert first.as_dict() == second.as_dict()
    transition = first.data["transition"]
    assert transition["result_hash"] == canonical_hash(first.data["next_state"])
    assert first.data["next_state"]["lineage"]["idempotency_key"] == \
        "discord-message-101"
    changed = propose(current, event, "discord-message-102")
    assert changed.data["transition"]["transition_id"] != \
        transition["transition_id"]


def test_commit_is_idempotent_without_server_side_state():
    current = state()
    proposal = propose(
        current, {"type": "action"}, "discord-message-103")
    transition = proposal.data["transition"]

    first = commit(current, transition)
    retry = commit(first.data["next_state"], transition)

    assert first.exit_code == retry.exit_code == 0
    assert first.data == retry.data
    assert first.data["commit"]["status"] == "verified"
    assert first.data["commit"]["persistence"] == "caller-owned"
    assert first.data["commit"]["result_hash"] == transition["result_hash"]
    assert first.data["commit"]["receipt_hash"].startswith("sha256:")


def test_concurrent_and_out_of_order_discord_events_conflict_then_reconcile():
    initial = state()
    action = propose(
        initial, {"type": "action"}, "discord-message-200")
    move = propose(
        initial, {"type": "move", "feet": 10}, "discord-message-201")

    action_commit = commit(initial, action.data["transition"])
    current = action_commit.data["next_state"]
    stale = commit(current, move.data["transition"])

    assert stale.exit_code == 2
    assert stale.data["reason_code"] == "stale-state"
    assert stale.data["recoverability"] == "conflict"
    assert stale.data["suggested_next_action"] == "reconcile-state"
    assert stale.data["expected_state_precondition_hash"] == \
        move.data["transition"]["state_precondition_hash"]
    assert stale.data["actual_state_hash"] == canonical_hash(current)
    assert "next_state" not in stale.data

    reconciled = propose(
        current, {"type": "move", "feet": 10}, "discord-message-201")
    committed = commit(current, reconciled.data["transition"])
    assert committed.exit_code == 0
    assert committed.data["next_state"]["turn"]["action_spent"] is True
    assert committed.data["next_state"]["turn"]["movement_ft_spent"] == 10


def test_tampered_proposal_and_false_retry_fail_closed():
    current = state()
    proposal = propose(
        current, {"type": "move", "feet": 5}, "discord-message-300")
    tampered = copy.deepcopy(proposal.data["transition"])
    tampered["result_hash"] = "sha256:" + "0" * 64
    rejected = commit(current, tampered)
    assert rejected.exit_code == 2
    assert rejected.data["reason_code"] == "invalid-input"

    unrelated = copy.deepcopy(proposal.data["next_state"])
    unrelated["lineage"]["idempotency_key"] = "different-event"
    unrelated["lineage"]["self"] = __import__("srdcheck").lineage.canon_hash(
        unrelated)
    false_retry = commit(unrelated, proposal.data["transition"])
    assert false_retry.exit_code == 2


def test_commit_normalizes_schema_integers_and_rejects_invalid_current_state():
    current = state()
    proposal = propose(
        current, {"type": "move", "feet": 5}, "discord-message-400")
    integral_float = copy.deepcopy(current)
    integral_float["speed"] = 30.0
    integral_float["turn"]["movement_ft_spent"] = 0.0
    accepted = commit(integral_float, proposal.data["transition"])
    assert accepted.exit_code == 0
    assert isinstance(accepted.data["next_state"]["speed"], int)

    invalid = copy.deepcopy(current)
    invalid["turn"]["action_spent"] = 0
    rejected = commit(invalid, proposal.data["transition"])
    assert rejected.exit_code == 2
    assert rejected.data["reason_code"] == "invalid-input"
    assert "next_state" not in rejected.data


def test_idempotency_keys_reject_blank_or_padded_values():
    for key in ("", "   ", " discord-message-500"):
        result = ENGINE.query("event.apply", {
            "state": state(), "event": {"type": "round-advance"},
            "idempotency_key": key,
        })
        assert result.exit_code == 2
        assert result.data["reason_code"] == "invalid-input"
        assert "next_state" not in result.data
