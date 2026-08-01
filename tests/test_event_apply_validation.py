"""Fail-closed state and conditional-fact contract for event.apply (#48)."""

import copy
import io
import json
import pathlib
import subprocess
import sys

import pytest

from srdcheck.engine import Engine
from srdcheck import lineage
from srdcheck.mcp import PROTOCOL_VERSION, Server
from srdcheck.schema import issues as schema_issues


ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"
E = Engine([ADAPTER])
FRESH_TURN = {
    "action_spent": False,
    "bonus_action_spent": False,
    "reaction_spent": False,
    "free_interaction_spent": False,
    "movement_ft_spent": 0,
    "spell_slots_spent_this_turn": 0,
}
SUPPORTED_EVENT_TYPES = {
    "turn-start", "round-advance", "action", "bonus-action", "reaction",
    "free-interaction", "move", "stand-up", "condition-gained",
    "condition-ended", "damage", "heal", "death-save", "ruling",
}


def state(**updates):
    value = {
        "speed": 30,
        "conditions": [],
        "turn": dict(FRESH_TURN),
        "dead": False,
        "stable": False,
        "death_save_successes": 0,
        "death_save_failures": 0,
    }
    value.update(updates)
    return value


def apply(current, event):
    return E.query("event.apply", {"state": current, "event": event})


def ready_mcp_server():
    server = Server([ADAPTER])
    init = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "event-test", "version": "1"},
        },
    })
    assert "result" in init
    server.handle({"jsonrpc": "2.0", "method":
                   "notifications/initialized"})
    return server


def mcp_apply(server, payload, request_id=2):
    reply = server.handle({
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": "event_apply", "arguments": payload},
    })
    return reply["result"]


def deeply_nested(depth=1500):
    value = {}
    for _ in range(depth):
        value = {"next": value}
    return value


def assert_refusal(result, reason, missing=()):
    assert result.exit_code == 2
    assert result.data["reason_code"] == reason
    assert result.data["missing_inputs"] == list(missing)
    assert "next_state" not in result.data


@pytest.mark.parametrize(("current", "path"), [
    ({"speed": 30, "conditions": [], "turn": {}},
     "state.turn.action_spent"),
    (state(turn={**FRESH_TURN, "action_spent": 0}),
     "state.turn.action_spent"),
    (state(conditions=[3]), "state.conditions[0]"),
    (state(lineage={"seq": "1"}), "state.lineage.seq"),
    ({**state(), "actor": {}}, "state.actor"),
    (state(conditions=["   "]), "state.conditions[0]"),
])
def test_structurally_invalid_state_is_invalid_input_without_mutation(
        current, path):
    before = copy.deepcopy(current)
    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "invalid-input")
    assert any(path in problem for problem in result.data["validation_errors"])
    assert current == before
    if "lineage" not in before:
        assert "lineage" not in current


def test_non_json_library_state_refuses_instead_of_raising():
    current = state(lineage={
        "seq": 1,
        "prev": "abc",
        "event": {"opaque": object()},
        "rule_ids": [],
        "kind": "rule",
        "self": "def",
    })

    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "invalid-input")
    assert "finite JSON values" in result.data["validation_errors"][0]


def test_integral_float_state_is_normalized_without_mutating_caller_state():
    current = state(
        speed=30.0,
        death_save_successes=0.0,
        death_save_failures=0.0,
        turn={**FRESH_TURN, "movement_ft_spent": 0.0,
              "spell_slots_spent_this_turn": 0.0},
    )
    before = copy.deepcopy(current)

    result = apply(current, {"type": "round-advance"})

    assert result.exit_code == 0
    next_state = result.data["next_state"]
    assert isinstance(next_state["speed"], int)
    assert isinstance(next_state["death_save_successes"], int)
    assert isinstance(next_state["turn"]["movement_ft_spent"], int)
    assert current == before
    assert isinstance(current["speed"], float)


def test_state_conditions_are_semantically_validated_before_every_fold():
    wrong_category = apply(
        state(conditions=["Fireball"]), {"type": "round-advance"})
    assert_refusal(wrong_category, "invalid-input")

    unknown = apply(
        state(conditions=["Hexcursed"]), {"type": "round-advance"})
    assert_refusal(unknown, "unsupported-content")

    exhaustion = apply(
        state(conditions=["Exhaustion"], exhaustion_level=1),
        {"type": "round-advance"})
    assert exhaustion.exit_code == 0

    missing_level = apply(
        state(conditions=["Exhaustion"]), {"type": "round-advance"})
    assert_refusal(
        missing_level, "missing-fact", ("state.exhaustion_level",))

    zero_level = apply(
        state(conditions=["Exhaustion"], exhaustion_level=0),
        {"type": "round-advance"})
    assert_refusal(zero_level, "invalid-input")

    orphan_level = apply(
        state(exhaustion_level=2), {"type": "round-advance"})
    assert_refusal(orphan_level, "invalid-input")


@pytest.mark.parametrize(("updates", "path"), [
    ({"conditions": [" Petrified "]}, "state.conditions[0]"),
    ({"resistances": [" fire"]}, "state.resistances[0]"),
    ({"immunities": ["cold "]}, "state.immunities[0]"),
    ({"vulnerabilities": [" lightning "]},
     "state.vulnerabilities[0]"),
    ({"conditions": ["Prone", "prone"]}, "state.conditions[1]"),
])
def test_canonical_state_tokens_reject_padding_and_duplicate_conditions(
        updates, path):
    current = state(**updates)
    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "invalid-input")
    assert any(path in error for error in result.data["validation_errors"])


@pytest.mark.parametrize(("updates", "reason", "missing", "path"), [
    ({"hp_max": 0}, "invalid-input", (), "state.hp_max"),
    ({"hp": 11, "hp_max": 10}, "invalid-input", (), "state.hp"),
    ({"hp": 1, "hp_max": 10, "dead": True},
     "invalid-input", (), "state.dead"),
    ({"hp": 0, "hp_max": 10, "dead": True, "stable": True},
     "invalid-input", (), "state.stable"),
    ({"death_save_successes": 3, "stable": False},
     "invalid-input", (), "state.stable"),
    ({"death_save_failures": 3, "dead": False},
     "invalid-input", (), "state.dead"),
    ({"hp": 4, "hp_max": 10, "death_save_successes": 1},
     "invalid-input", (), "state.death_save_successes"),
    ({"hp": 4, "hp_max": 10, "death_save_failures": 2},
     "invalid-input", (), "state.death_save_failures"),
])
def test_provable_lifecycle_contradictions_fail_closed(
        updates, reason, missing, path):
    current = state(**updates)
    before = copy.deepcopy(current)
    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, reason, missing)
    assert any(path in error for error in result.data["validation_errors"])
    assert current == before
    assert "lineage" not in current


def test_zero_hp_monster_needs_explicit_dead_result_without_successor():
    current = state(hp=0, hp_max=10, is_monster=True)
    current.pop("dead")
    before = copy.deepcopy(current)

    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "missing-fact", ("state.dead",))
    assert "next_state" not in result.data
    assert current == before
    assert "lineage" not in current


def test_agent_dm_can_rule_monster_unconscious_and_then_make_death_save():
    current = state(hp=5, hp_max=12, is_monster=True)

    ruling = apply(current, {
        "type": "ruling",
        "note": "This important foe uses character-style death saves.",
        "state_patch": {
            "hp": 0,
            "dead": False,
            "conditions": ["Unconscious"],
        },
    })

    assert ruling.exit_code == 0, ruling.why
    opted_out = ruling.data["next_state"]
    assert opted_out["is_monster"] is True
    assert opted_out["hp"] == 0
    assert opted_out["dead"] is False
    assert opted_out["lineage"]["kind"] == "ruling"

    death_save = apply(opted_out, {"type": "death-save", "result": 12})
    assert death_save.exit_code == 0, death_save.why
    saved = death_save.data["next_state"]
    assert saved["death_save_successes"] == 1
    assert saved["dead"] is False


def test_standard_damage_still_kills_a_monster_at_zero():
    result = apply(
        state(hp=5, hp_max=12, is_monster=True),
        {"type": "damage", "amount": 5},
    )

    assert result.exit_code == 0, result.why
    nxt = result.data["next_state"]
    assert nxt["hp"] == 0
    assert nxt["dead"] is True
    assert "hp.monster-death" in result.rule_ids


@pytest.mark.parametrize(("counter", "flag", "missing"), [
    ("death_save_successes", "stable", "state.stable"),
    ("death_save_failures", "dead", "state.dead"),
])
def test_terminal_save_counter_needs_explicit_resulting_flag(
        counter, flag, missing):
    current = state(**{counter: 3})
    current.pop(flag)

    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "missing-fact", (missing,))


def test_ruling_patch_cannot_inject_a_non_condition_into_state():
    current = state()
    before = copy.deepcopy(current)
    result = apply(current, {
        "type": "ruling",
        "note": "Bad category",
        "state_patch": {"conditions": ["Fireball"]},
    })

    assert_refusal(result, "invalid-input")
    assert current == before
    assert "lineage" not in current


def test_exhaustion_gain_and_end_refuse_until_level_aware_event_exists():
    gained = apply(
        state(), {"type": "condition-gained", "name": "Exhaustion"})
    assert_refusal(gained, "unmodeled-rule")

    ended = apply(
        state(conditions=["Exhaustion"], exhaustion_level=2),
        {"type": "condition-ended", "name": "Exhaustion"})
    assert_refusal(ended, "unmodeled-rule")


def test_agent_dm_can_record_complete_exhaustion_state_as_a_ruling():
    gained = apply(state(), {
        "type": "ruling",
        "note": "The trap applies two levels of Exhaustion.",
        "state_patch": {
            "conditions": ["Exhaustion"], "exhaustion_level": 2,
        },
    })
    assert gained.exit_code == 0
    exhausted = gained.data["next_state"]
    assert exhausted["exhaustion_level"] == 2

    ended = apply(exhausted, {
        "type": "ruling",
        "note": "The restorative effect ends Exhaustion.",
        "state_patch": {"conditions": [], "exhaustion_level": 0},
    })
    assert ended.exit_code == 0
    recovered = ended.data["next_state"]
    assert recovered["conditions"] == []
    assert recovered["exhaustion_level"] == 0


@pytest.mark.parametrize(("name", "reason", "exit_code"), [
    ("Fireball", "invalid-input", 2),
    ("Hexcursed", "unsupported-content", 2),
    ("Blinded", None, 1),
])
def test_condition_ended_gates_content_before_membership(
        name, reason, exit_code):
    result = apply(state(), {"type": "condition-ended", "name": name})

    assert result.exit_code == exit_code
    assert "next_state" not in result.data
    if reason:
        assert result.data["reason_code"] == reason


@pytest.mark.parametrize(("current", "event", "missing"), [
    (state(), {"type": "move"}, ("event.feet",)),
    (state(), {"type": "condition-gained"}, ("event.name",)),
    (state(conditions=["Prone"]), {"type": "condition-ended"},
     ("event.name",)),
    (state(hp=8, hp_max=10), {"type": "damage"}, ("event.amount",)),
    (state(hp=8), {"type": "damage", "amount": 1}, ("state.hp_max",)),
    (state(hp=8, hp_max=10), {"type": "heal"}, ("event.amount",)),
    (state(), {"type": "ruling"}, ("event.note",)),
    (state(hp=0, conditions=["Unconscious"]), {"type": "death-save"},
     ("event.result",)),
])
def test_missing_conditional_facts_have_exact_paths_and_no_successor(
        current, event, missing):
    before = copy.deepcopy(current)
    result = apply(current, event)

    assert_refusal(result, "missing-fact", missing)
    assert result.data["suggested_next_action"] == "provide-facts"
    assert current == before


def test_eligible_death_save_requires_explicit_eligibility_and_counters():
    current = {
        "speed": 30,
        "conditions": ["Unconscious"],
        "turn": dict(FRESH_TURN),
        "hp": 0,
    }
    result = apply(current, {"type": "death-save", "result": 10})
    assert_refusal(result, "missing-fact", (
        "state.dead",
        "state.stable",
        "state.death_save_successes",
        "state.death_save_failures",
    ))


@pytest.mark.parametrize("current", [
    state(hp=4),
    state(hp=0, dead=True),
    state(hp=0, stable=True),
])
def test_known_ineligible_death_save_is_illegal_without_asking_for_roll(
        current):
    result = apply(current, {"type": "death-save"})

    assert result.exit_code == 1
    assert "death-save.mechanic" in result.rule_ids
    assert not result.data
    assert "lineage" not in current


def test_damage_at_zero_requires_only_facts_that_can_change_the_result():
    no_dead = state(hp=0, hp_max=20)
    no_dead.pop("dead")
    result = apply(no_dead, {"type": "damage", "amount": 1, "crit": False})
    assert_refusal(result, "missing-fact", ("state.dead",))

    no_failures = state(hp=0, hp_max=20)
    no_failures.pop("death_save_failures")
    result = apply(
        no_failures, {"type": "damage", "amount": 1, "crit": False})
    assert_refusal(result, "missing-fact", ("state.death_save_failures",))

    result = apply(state(hp=0, hp_max=20),
                   {"type": "damage", "amount": 1})
    assert_refusal(result, "missing-fact", ("event.crit",))


@pytest.mark.parametrize(("current", "event"), [
    (state(hp=0, hp_max=20),
     {"type": "damage", "amount": 0}),
    (state(hp=0, hp_max=20, immunities=["fire"]),
     {"type": "damage", "amount": 10, "damage_type": "fire"}),
])
def test_zero_effective_damage_at_zero_adds_no_death_save_failure(
        current, event):
    current.pop("death_save_failures")
    current.pop("dead")
    result = apply(current, event)

    assert result.exit_code == 0
    nxt = result.data["next_state"]
    assert "death_save_failures" not in nxt
    assert "death-save.damage-at-0" not in result.rule_ids


def test_specific_damage_traits_require_a_nonblank_damage_type():
    current = state(hp=10, hp_max=10, resistances=["fire"])
    absent = apply(current, {"type": "damage", "amount": 2})
    assert_refusal(absent, "missing-fact", ("event.damage_type",))

    blank = apply(
        current, {"type": "damage", "amount": 2, "damage_type": "   "})
    assert_refusal(blank, "invalid-input")


def test_known_dead_damage_does_not_request_irrelevant_damage_type():
    result = apply(
        state(hp=0, hp_max=10, dead=True, resistances=["fire"]),
        {"type": "damage", "amount": 2})
    assert result.exit_code == 0
    assert result.data["next_state"]["dead"] is True

    no_hp_facts = apply(
        state(dead=True, resistances=["fire"]),
        {"type": "damage", "amount": 2})
    assert no_hp_facts.exit_code == 0
    assert no_hp_facts.data["next_state"]["dead"] is True


def test_heal_at_zero_requires_explicit_not_dead_fact():
    current = state(hp=0, hp_max=20, conditions=["Unconscious"])
    current.pop("dead")

    result = apply(current, {"type": "heal", "amount": 5})

    assert_refusal(result, "missing-fact", ("state.dead",))


def test_drop_to_zero_derives_complete_known_lifecycle_state():
    current = state(hp=5, hp_max=20)
    for field in ("dead", "stable", "death_save_successes",
                  "death_save_failures"):
        current.pop(field)

    result = apply(current, {"type": "damage", "amount": 5})

    assert result.exit_code == 0
    nxt = result.data["next_state"]
    assert {key: nxt[key] for key in (
        "dead", "stable", "death_save_successes",
        "death_save_failures")} == {
            "dead": False, "stable": False,
            "death_save_successes": 0, "death_save_failures": 0,
        }


def test_all_damage_trait_does_not_need_a_specific_damage_type():
    result = apply(
        state(hp=10, hp_max=10, resistances=["all"]),
        {"type": "damage", "amount": 5})
    assert result.exit_code == 0
    assert result.data["next_state"]["hp"] == 8


def test_supplied_nested_event_shapes_fail_closed():
    missing_level = apply(state(), {"type": "action", "spell": {}})
    assert_refusal(missing_level, "missing-fact", ("event.spell.level",))

    bad_level = apply(
        state(), {"type": "action", "spell": {"level": "one"}})
    assert_refusal(bad_level, "invalid-input")

    blank_concentration = apply(
        state(), {"type": "action", "concentration_on": "  "})
    assert_refusal(blank_concentration, "invalid-input")

    padded_concentration = apply(
        state(), {
            "type": "action", "spell": {"level": 1},
            "concentration_on": " Bless ",
        })
    assert_refusal(padded_concentration, "invalid-input")

    missing_spell = apply(
        state(), {"type": "action", "concentration_on": "Bless"})
    assert_refusal(missing_spell, "missing-fact", ("event.spell",))


@pytest.mark.parametrize(("current", "event", "bad_field"), [
    (state(), {"type": "turn-start", "amount": 1}, "amount"),
    (state(), {"type": "round-advance", "amount": 1}, "amount"),
    (state(), {"type": "action", "feet": 1}, "feet"),
    (state(), {"type": "bonus-action", "feet": 1}, "feet"),
    (state(), {"type": "reaction", "feet": 1}, "feet"),
    (state(), {"type": "free-interaction", "spell": {"level": 0}},
     "spell"),
    (state(), {"type": "move", "feet": 1, "note": "ignored"}, "note"),
    (state(conditions=["Prone"]), {"type": "stand-up", "feet": 1},
     "feet"),
    (state(), {"type": "condition-gained", "name": "Blinded", "amount": 1},
     "amount"),
    (state(conditions=["Prone"]),
     {"type": "condition-ended", "name": "Prone", "amount": 1},
     "amount"),
    (state(hp=10, hp_max=10),
     {"type": "damage", "amount": 1, "note": "ignored"}, "note"),
    (state(hp=5, hp_max=10),
     {"type": "heal", "amount": 1, "crit": False}, "crit"),
    (state(hp=0, conditions=["Unconscious"]),
     {"type": "death-save", "result": 10, "amount": 1}, "amount"),
    (state(), {"type": "ruling", "note": "Table decision", "amount": 1},
     "amount"),
])
def test_every_event_rejects_fields_it_would_otherwise_ignore(
        current, event, bad_field):
    before = copy.deepcopy(current)
    result = apply(current, event)

    assert_refusal(result, "invalid-input")
    assert result.data["unknown_fields"] == [f"event.{bad_field}"]
    assert current == before


def test_ruling_requires_note_and_validates_full_optional_patch():
    blank = apply(state(), {"type": "ruling", "note": "   "})
    assert_refusal(blank, "invalid-input")

    note_only = apply(state(), {"type": "ruling", "note": "Rule of cool"})
    assert note_only.exit_code == 0
    assert note_only.data["next_state"]["lineage"]["kind"] == "ruling"

    current = state()
    before = copy.deepcopy(current)
    bad_patch = apply(current, {
        "type": "ruling",
        "note": "Incomplete turn replacement",
        "state_patch": {"turn": {}},
    })
    assert_refusal(bad_patch, "invalid-input")
    assert current == before
    assert "lineage" not in current


@pytest.mark.parametrize("state_patch", [
    {"concentration_on": "   "},
    {"conditions": ["Prone", "prone"]},
    {"hp": 11, "hp_max": 10},
    {"dead": True, "stable": True},
    {"conditions": ["Exhaustion"], "exhaustion_level": 0},
])
def test_ruling_candidate_runs_full_semantic_validation(state_patch):
    current = state(hp=5, hp_max=10)
    before = copy.deepcopy(current)

    result = apply(current, {
        "type": "ruling", "note": "Attempted patch",
        "state_patch": state_patch,
    })

    assert result.exit_code == 2
    assert "next_state" not in result.data
    assert current == before


def test_lineage_owns_a_copy_of_the_declared_event():
    event = {"type": "action", "spell": {"level": 1}}
    result = apply(state(), event)
    assert result.exit_code == 0

    event["spell"]["level"] = 9

    assert result.data["next_state"]["lineage"]["event"]["spell"]["level"] == 1


@pytest.mark.parametrize(("field", "replacement"), [
    ("seq", 7),
    ("prev", "tampered-predecessor"),
    ("event", {"type": "move", "feet": 5}),
    ("rule_ids", ["damage.reduces-hp"]),
    ("kind", "ruling"),
])
def test_lineage_self_commits_to_each_metadata_field(field, replacement):
    first = apply(state(), {"type": "round-advance"})
    assert first.exit_code == 0
    current = copy.deepcopy(first.data["next_state"])
    original_self = current["lineage"]["self"]
    current["lineage"][field] = replacement
    before = copy.deepcopy(current)

    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "invalid-input")
    assert "state.lineage.self" in result.data["validation_errors"][0]
    assert current["lineage"]["self"] == original_self
    assert current == before
    assert "next_state" not in result.data


def test_legacy_payload_only_lineage_hash_fails_closed_for_reanchoring():
    first = apply(state(), {"type": "round-advance"})
    assert first.exit_code == 0
    current = copy.deepcopy(first.data["next_state"])
    payload = {key: value for key, value in current.items()
               if key != "lineage"}
    current["lineage"]["self"] = lineage.canon_hash(payload)
    before = copy.deepcopy(current)

    result = apply(current, {"type": "round-advance"})

    assert_refusal(result, "invalid-input")
    assert "state.lineage.self" in result.data["validation_errors"][0]
    assert "next_state" not in result.data
    assert current == before


def test_lineage_success_chain_commits_metadata_and_links_prior_self():
    bootstrap = state()
    first_event = {"type": "round-advance"}
    first = apply(bootstrap, first_event)
    assert first.exit_code == 0
    one = first.data["next_state"]

    assert one["lineage"]["prev"] == lineage.canon_hash(bootstrap)
    assert one["lineage"]["self"] == lineage.canon_hash(one)

    second_event = {"type": "ruling", "note": "The table resolves a tie."}
    second = apply(one, second_event)
    assert second.exit_code == 0
    two = second.data["next_state"]

    assert two["lineage"]["prev"] == one["lineage"]["self"]
    assert two["lineage"]["self"] == lineage.canon_hash(two)
    assert two["lineage"]["event"] == second_event
    assert two["lineage"]["kind"] == "ruling"


EVENT_REFUSAL_CASES = [
    ({"speed": 30, "conditions": [], "turn": {}},
     {"type": "turn-start"}),
    ({"speed": 30, "conditions": [], "turn": {}},
     {"type": "round-advance"}),
    (state(turn={**FRESH_TURN, "action_spent": True}), {"type": "action"}),
    (state(turn={**FRESH_TURN, "bonus_action_spent": True}),
     {"type": "bonus-action"}),
    (state(turn={**FRESH_TURN, "reaction_spent": True}),
     {"type": "reaction"}),
    (state(turn={**FRESH_TURN, "free_interaction_spent": True}),
     {"type": "free-interaction"}),
    (state(), {"type": "move"}),
    (state(), {"type": "stand-up"}),
    (state(), {"type": "condition-gained"}),
    (state(conditions=["Prone"]), {"type": "condition-ended"}),
    (state(hp=10, hp_max=10), {"type": "damage"}),
    (state(hp=5, hp_max=10), {"type": "heal"}),
    (state(hp=0, conditions=["Unconscious"]), {"type": "death-save"}),
    (state(), {"type": "ruling"}),
]


def test_refusal_matrix_covers_all_declared_event_types():
    assert {event["type"] for _, event in EVENT_REFUSAL_CASES} == \
        SUPPORTED_EVENT_TYPES


@pytest.mark.parametrize(("current", "event"), EVENT_REFUSAL_CASES)
def test_every_event_has_an_omission_or_boundary_with_no_successor(
        current, event):
    current = copy.deepcopy(current)
    before = copy.deepcopy(current)

    result = apply(current, event)

    assert result.exit_code in {1, 2}
    assert "next_state" not in result.data
    assert current == before
    assert "lineage" not in current


def test_legacy_actor_shaped_v05_state_is_invalid_without_a_successor():
    legacy = {
        "round": 1,
        "turn": {"actor": "hero", "spent": {}},
        "actors": {},
        "conditions": [],
    }
    before = copy.deepcopy(legacy)

    result = apply(legacy, {"type": "action"})

    assert_refusal(result, "invalid-input")
    assert "next_state" not in result.data
    assert legacy == before


@pytest.mark.parametrize(("current", "event"), [
    (state(), {"type": "turn-start"}),
    (state(), {"type": "round-advance"}),
    (state(), {"type": "action"}),
    (state(), {"type": "bonus-action"}),
    (state(), {"type": "reaction"}),
    (state(), {"type": "free-interaction"}),
    (state(), {"type": "move", "feet": 0}),
    (state(conditions=["Prone"]), {"type": "stand-up"}),
    (state(), {"type": "condition-gained", "name": "Blinded"}),
    (state(conditions=["Prone"]),
     {"type": "condition-ended", "name": "Prone"}),
    (state(hp=10, hp_max=10), {"type": "damage", "amount": 1}),
    (state(hp=5, hp_max=10), {"type": "heal", "amount": 1}),
    (state(hp=0, conditions=["Unconscious"]),
     {"type": "death-save", "result": 10}),
    (state(), {"type": "ruling", "note": "Table decision"}),
])
def test_every_supported_event_has_a_complete_successful_transition(
        current, event):
    before = copy.deepcopy(current)
    result = apply(current, event)

    assert result.exit_code == 0, result.why
    nxt = result.data["next_state"]
    assert nxt["lineage"]["event"] == event
    assert current == before
    schema = json.loads((ADAPTER / "state_schema.json").read_text())["schema"]
    assert schema_issues(nxt, schema, path="state") == []
    following = apply(nxt, {"type": "round-advance"})
    assert following.exit_code == 0, following.why


def test_mcp_publishes_canonical_state_schema_and_returns_a_verdict():
    canonical = json.loads(
        (ADAPTER / "state_schema.json").read_text(encoding="utf-8"))["schema"]
    server = Server([ADAPTER])
    tool = next(tool for tool in server.tools if tool["name"] == "event_apply")
    assert tool["inputSchema"]["properties"]["state"] == canonical

    init = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "event-test", "version": "1"},
        },
    })
    assert "result" in init
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    reply = server.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "event_apply",
            "arguments": {
                "state": {"speed": 30, "conditions": [], "turn": {}},
                "event": {"type": "move", "feet": 5},
            },
        },
    })
    result = reply["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["exit_code"] == 2
    assert result["structuredContent"]["data"]["reason_code"] == "invalid-input"


@pytest.mark.parametrize("payload", [
    {"state": state(), "event": {"type": "round-advance"}},
    {"state": state(), "event": {"type": "move"}},
    {"state": {"speed": 30, "conditions": [], "turn": {}},
     "event": {"type": "round-advance"}},
])
def test_raw_adapter_handle_matches_engine_dispatch(payload):
    adapter = E.adapters[0]
    before = copy.deepcopy(payload)

    direct = adapter.handle("event.apply", payload)
    dispatched = E.query("event.apply", payload)

    assert direct.as_dict() == dispatched.as_dict()
    assert payload == before


@pytest.mark.parametrize("payload", [
    {
        "state": {
            "round": 1, "actors": {}, "conditions": [],
            "turn": {"actor": "hero", "spent": {}},
        },
        "event": {"type": "action"},
    },
    {"state": state(), "event": {"type": "move"}},
    {"state": state(),
     "event": {"type": "ruling", "note": "bad", "state_patch": {"turn": {}}}},
    {"state": state(conditions=["Exhaustion"]),
     "event": {"type": "round-advance"}},
])
def test_schema_valid_raw_direct_call_corpus_never_raises_or_succeeds(
        payload):
    adapter = E.adapters[0]
    shallow = adapter.query_meta["event.apply"]["inputSchema"]
    assert schema_issues(payload, shallow) == []

    result = adapter.handle("event.apply", payload)

    assert result.exit_code == 2
    assert "next_state" not in result.data


@pytest.mark.parametrize("payload", [
    [],
    {"state": [], "event": {"type": "round-advance"}},
    {"state": state(), "event": []},
    {"state": state(), "event": {"type": "action", "spell": {}}},
])
def test_raw_protocol_bypass_corpus_returns_verdict_instead_of_raising(payload):
    result = E.adapters[0].handle("event.apply", payload)

    assert result.exit_code == 2
    assert "next_state" not in result.data


def test_deep_open_lineage_event_is_a_structured_refusal_everywhere():
    payload = {
        "state": state(lineage={
            "seq": 1, "prev": "prev", "event": deeply_nested(),
            "rule_ids": [], "kind": "rule", "self": "self",
        }),
        "event": {"type": "round-advance"},
    }
    shallow = E.adapters[0].query_meta["event.apply"]["inputSchema"]
    assert schema_issues(payload, shallow) == []

    direct = E.adapters[0].handle("event.apply", payload)
    dispatched = E.query("event.apply", payload)
    mcp = mcp_apply(ready_mcp_server(), payload)

    for result in (direct.as_dict(), dispatched.as_dict(),
                   mcp["structuredContent"]):
        assert result["exit_code"] == 2
        assert result["data"]["reason_code"] == "invalid-input"
        assert "next_state" not in result["data"]
    assert mcp["isError"] is False


def test_deep_json_parse_boundaries_do_not_crash_cli_or_mcp_stdio():
    deep_json = '{"next":' * 10000 + "0" + "}" * 10000

    out = io.StringIO()
    Server([ADAPTER]).serve(io.StringIO(deep_json + "\n"), out)
    response = json.loads(out.getvalue())
    assert response["error"]["code"] == -32700

    completed = subprocess.run(
        [sys.executable, "-m", "srdcheck", "query", "event.apply",
         deep_json],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 3
    assert json.loads(completed.stdout)["error"].startswith("bad input:")
    assert "Traceback" not in completed.stderr


def test_cli_missing_event_fact_matches_library_contract():
    payload = {
        "state": state(hp=10, hp_max=10),
        "event": {"type": "damage"},
    }
    completed = subprocess.run(
        [sys.executable, "-m", "srdcheck", "query", "event.apply",
         json.dumps(payload)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    result = json.loads(completed.stdout)
    assert completed.returncode == result["exit_code"] == 2
    assert result["data"]["reason_code"] == "missing-fact"
    assert result["data"]["missing_inputs"] == ["event.amount"]


@pytest.mark.parametrize("payload", [
    {"state": state(), "event": {"type": "round-advance"}},
    {"state": state(hp=10, hp_max=10), "event": {"type": "damage"}},
    {"state": {"speed": 30, "conditions": [], "turn": {}},
     "event": {"type": "move", "feet": 5}},
])
def test_library_cli_and_mcp_have_failure_and_success_parity(payload):
    expected = E.query("event.apply", payload).as_dict()
    completed = subprocess.run(
        [sys.executable, "-m", "srdcheck", "query", "event.apply",
         json.dumps(payload)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    mcp = mcp_apply(ready_mcp_server(), payload)["structuredContent"]

    assert completed.returncode == expected["exit_code"]
    assert json.loads(completed.stdout) == expected
    assert mcp == expected


def test_mcp_schema_reference_is_a_strict_drift_rachet():
    meta = E.adapters[0].query_meta["event.apply"]
    assert meta["inputSchemaPropertyRefs"] == {
        "state": "state_schema.json#/schema",
    }
