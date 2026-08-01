"""SRD adapter routing for the machine-readable exit-2 recovery contract."""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402


E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def assert_recovery(result, reason, recoverability, action, missing=()):
    assert result.exit_code == 2
    assert result.data["reason_code"] == reason
    assert result.data["recoverability"] == recoverability
    assert result.data["suggested_next_action"] == action
    assert result.data["missing_inputs"] == list(missing)


@pytest.mark.parametrize(
    ("query_type", "params", "reason", "recoverability", "action", "missing"),
    [
        ("mage-hand.use", {"kind": "manipulate_object", "weight_lb": -1},
         "invalid-input", "retry", "repair-request", ()),
        ("opportunity-attack.provoked", {},
         "missing-fact", "retry", "provide-facts", ("movement_kind",)),
        ("creature.valid", {"name": "Not An SRD Creature"},
         "unsupported-content", "alternate-path", "select-adapter", ()),
        ("passive.perception", {"advantage": True},
         "unmodeled-rule", "alternate-path", "use-other-capability", ()),
        ("attack.modifiers",
         {"attacker": {"can_see_target": True},
          "target": {"conditions": ["Invisible"]}, "distance_ft": 10},
         "rules-ambiguous", "authority", "resolve-table-ruling", ()),
        ("mage-hand.use", {"kind": "pick_a_pocket"},
         "gm-discretion", "authority", "resolve-table-ruling", ()),
    ],
)
def test_all_six_refusal_classes_route_without_parsing_why(
        query_type, params, reason, recoverability, action, missing):
    result = E.query(query_type, params)
    assert_recovery(result, reason, recoverability, action, missing)
    if recoverability == "authority":
        assert result.data["required_authority"] == "dm"
        assert "human" not in result.why.lower()
    else:
        assert "required_authority" not in result.data


def test_missing_fact_paths_are_exact_and_path_sensitive():
    both = E.query(
        "opportunity-attack.provoked", {"movement_kind": "voluntary"})
    assert_recovery(
        both, "missing-fact", "retry", "provide-facts",
        ("leaves_reach", "mover_seen_by_reactor"))

    one = E.query("opportunity-attack.provoked", {
        "movement_kind": "voluntary", "leaves_reach": True})
    assert_recovery(
        one, "missing-fact", "retry", "provide-facts",
        ("mover_seen_by_reactor",))

    state = {"speed": 30, "conditions": [], "turn": {}, "hp": 4}
    damage = E.query(
        "event.apply", {"state": state, "event": {"type": "damage",
                                                    "amount": 1}})
    assert_recovery(
        damage, "missing-fact", "retry", "provide-facts", ("state.hp_max",))


@pytest.mark.parametrize("query_type,base", [
    ("turn.plan", {"speed": 30, "plan": []}),
    ("turn.options", {"speed": 30}),
])
def test_exhaustion_omission_is_missing_but_present_zero_is_invalid(
        query_type, base):
    omitted = E.query(query_type, {**base, "conditions": ["Exhaustion"]})
    assert_recovery(
        omitted, "missing-fact", "retry", "provide-facts",
        ("exhaustion_level",))

    zero = E.query(query_type, {
        **base, "conditions": ["Exhaustion"], "exhaustion_level": 0,
    })
    assert_recovery(zero, "invalid-input", "retry", "repair-request")


@pytest.mark.parametrize("query_type", ["save.check", "check.make"])
def test_integral_float_dc_is_present_and_normalized_not_requested_again(
        query_type):
    result = E.query(query_type, {"dc": 12.0})
    assert result.exit_code == 0
    assert result.data["dc"] == 12


@pytest.mark.parametrize("query_type,params", [
    ("mage-hand.use", {"kind": "   "}),
    ("creature.valid", {"name": "   "}),
    ("creature.stats", {"name": "   "}),
    ("spell.facts", {"name": "   "}),
    ("feature.uses", {"feature": ""}),
    ("event.apply", {
        "state": {},
        "event": {"type": "condition-gained", "name": "   "},
    }),
])
def test_present_blank_conditional_fact_is_invalid_not_missing(
        query_type, params):
    result = E.query(query_type, params)
    assert_recovery(result, "invalid-input", "retry", "repair-request")


def test_mage_hand_normalizes_padding_before_deterministic_matching():
    granted = E.query("mage-hand.use", {"kind": " manipulate_object "})
    prohibited = E.query("mage-hand.use", {"kind": " attack "})

    assert granted.exit_code == 0
    assert granted.verdict == "legal"
    assert prohibited.exit_code == 1
    assert prohibited.verdict == "illegal"


@pytest.mark.parametrize("query_type,params", [
    ("turn.plan", {"speed": 30, "plan": [], "conditions": ["   "]}),
    ("turn.options", {"speed": 30, "conditions": ["   "]}),
    ("reaction.available", {
        "spent_since_turn_start": False, "conditions": ["   "],
    }),
    ("attack.modifiers", {
        "attacker": {"conditions": ["   "]}, "target": {},
        "distance_ft": 5,
    }),
    ("save.check", {"dc": 12, "saver_conditions": ["   "]}),
    ("check.make", {"dc": 12, "actor_conditions": ["   "]}),
])
def test_blank_condition_name_is_repaired_not_routed_to_another_adapter(
        query_type, params):
    result = E.query(query_type, params)
    assert_recovery(result, "invalid-input", "retry", "repair-request")


def test_condition_category_split_routes_repair_adapter_or_capability(monkeypatch):
    unknown = E.query("reaction.available", {
        "spent_since_turn_start": False, "conditions": ["Hexcursed"]})
    assert_recovery(
        unknown, "unsupported-content", "alternate-path", "select-adapter")

    wrong_category = E.query("reaction.available", {
        "spent_since_turn_start": False, "conditions": ["Fireball"]})
    assert_recovery(
        wrong_category, "invalid-input", "retry", "repair-request")

    # Exercise the real-condition/unmodeled branch without claiming that a
    # currently modeled SRD condition is absent from the production registry.
    handler_globals = E.adapters[0]._handlers["turn.plan"].__globals__
    modeled = handler_globals["_MODELED_CONDITIONS"]
    monkeypatch.setitem(
        handler_globals, "_MODELED_CONDITIONS", modeled - {"charmed"})
    unmodeled = E.query(
        "turn.plan", {"speed": 30, "conditions": ["Charmed"], "plan": []})
    assert_recovery(
        unmodeled, "unmodeled-rule", "alternate-path",
        "use-other-capability")


def test_known_wrong_capability_overrides_adapter_selection_only():
    stats = E.query("creature.stats", {"name": "Fireball"})
    assert_recovery(
        stats, "unsupported-content", "alternate-path",
        "use-other-capability")

    spell = E.query("spell.facts", {"name": "Goblin Warrior"})
    assert_recovery(
        spell, "unsupported-content", "alternate-path",
        "use-other-capability")

    unknown = E.query("creature.stats", {"name": "Not An SRD Creature"})
    assert_recovery(
        unknown, "unsupported-content", "alternate-path", "select-adapter")


def test_indirect_turn_options_and_event_apply_preserve_recovery_metadata():
    options = E.query(
        "turn.options", {"speed": 30, "conditions": ["Hexcursed"]})
    assert_recovery(
        options, "unsupported-content", "alternate-path", "select-adapter")

    state = {
        "speed": 30,
        "conditions": ["Hexcursed"],
        "turn": {
            "action_spent": False,
            "bonus_action_spent": False,
            "reaction_spent": False,
            "free_interaction_spent": False,
            "movement_ft_spent": 0,
            "spell_slots_spent_this_turn": 0,
        },
    }
    applied = E.query(
        "event.apply", {"state": state, "event": {"type": "action"}})
    assert_recovery(
        applied, "unsupported-content", "alternate-path", "select-adapter")


def test_event_apply_remaps_and_consumes_exhaustion_state_fact():
    state = {"speed": 30, "conditions": ["Exhaustion"]}
    absent = E.query(
        "event.apply", {"state": state, "event": {"type": "action"}})
    assert_recovery(
        absent, "missing-fact", "retry", "provide-facts",
        ("state.exhaustion_level",))

    supplied = E.query("event.apply", {
        "state": {**state, "exhaustion_level": 2},
        "event": {"type": "action"},
    })
    assert supplied.exit_code == 0
    next_state = supplied.data["next_state"]
    assert next_state["exhaustion_level"] == 2
    assert next_state["turn"]["action_spent"] is True

    illegal = E.query("event.apply", {
        "state": {
            "speed": 30, "conditions": [],
            "turn": {"action_spent": True},
        },
        "event": {"type": "action"},
    })
    assert illegal.exit_code == 1


def test_agent_dm_authority_is_direct_not_a_human_escalation():
    discretionary = E.query("mage-hand.use", {"kind": "pick_a_pocket"})
    ambiguous = E.query("attack.modifiers", {
        "attacker": {"can_see_target": True},
        "target": {"conditions": ["Invisible"]},
        "distance_ft": 10,
    })
    for result in (discretionary, ambiguous):
        assert result.data["required_authority"] == "dm"
        assert result.data["suggested_next_action"] == "resolve-table-ruling"
        assert "calling agent when it is the dm" in result.why.lower()
        assert "human" not in result.why.lower()


def test_agent_facing_tool_metadata_treats_agent_dm_as_primary_authority():
    queries = E.adapters[0].query_meta
    mage_hand = queries["mage-hand.use"]["description"]
    ruling_event = queries["event.apply"]["description"]
    assert "authorized agent-DM may rule directly" in mage_hand
    assert "including the calling agent-DM" in ruling_event
