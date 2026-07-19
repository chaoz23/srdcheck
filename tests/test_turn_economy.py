"""Turn-economy goldens — several ported from the Phase 0 eval set."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def plan(steps, **kw):
    return E.query("turn.plan", {"speed": 30, "plan": steps, **kw})


def test_two_bonus_actions_illegal():  # eval ae-01 / ss-03
    v = plan([{"do": "bonus-action"}, {"do": "bonus-action"}])
    assert v.exit_code == 1
    assert "turn.one-bonus-action" in v.rule_ids


def test_split_movement_legal():  # eval ae-03
    v = plan([{"do": "move", "feet": 10}, {"do": "action"},
              {"do": "move", "feet": 20}])
    assert v.exit_code == 0
    assert "turn.break-up-move" in v.rule_ids


def test_movement_budget_exceeded():
    v = plan([{"do": "move", "feet": 20}, {"do": "move", "feet": 20}])
    assert v.exit_code == 1
    assert "turn.movement-budget" in v.rule_ids


def test_two_slot_spells_illegal():  # eval sp-01
    v = plan([{"do": "bonus-action", "spell": {"level": 2}},
              {"do": "action", "spell": {"level": 3}}])
    assert v.exit_code == 1
    assert "spell.one-slot-per-turn" in v.rule_ids


def test_bonus_cantrip_plus_slot_spell_legal():  # eval sp-02 (edition trap)
    v = plan([{"do": "bonus-action", "spell": {"level": 0}},
              {"do": "action", "spell": {"level": 1}}])
    assert v.exit_code == 0


def test_prone_grappled_cannot_stand():  # eval ss-05
    v = plan([{"do": "stand-up"}], conditions=["Prone", "Grappled"])
    assert v.exit_code == 1
    assert "condition.prone.movement" in v.rule_ids


def test_prone_stand_costs_half_speed():
    v = plan([{"do": "stand-up"}, {"do": "move", "feet": 15}],
             conditions=["Prone"])
    assert v.exit_code == 0
    v = plan([{"do": "stand-up"}, {"do": "move", "feet": 16}],
             conditions=["Prone"])
    assert v.exit_code == 1


def test_prone_move_requires_crawl():
    assert plan([{"do": "move", "feet": 10}], conditions=["Prone"]).exit_code == 1
    v = plan([{"do": "move", "feet": 10, "crawl": True}], conditions=["Prone"])
    assert v.exit_code == 0
    assert "movement.crawling-cost" in v.rule_ids


def test_incapacitated_blocks_everything():  # eval glossary p184
    for step in ({"do": "action"}, {"do": "bonus-action"}, {"do": "reaction"}):
        v = plan([step], conditions=["Incapacitated"])
        assert v.exit_code == 1
        assert "condition.incapacitated.inactive" in v.rule_ids


def test_unknown_condition_exit_2():
    assert plan([{"do": "action"}], conditions=["Hexcursed"]).exit_code == 2


def test_stunned_is_incapacitated_cant_act():
    # Stunned is now modeled: it embeds Incapacitated, so taking an action is
    # illegal (not an unbuilt refusal).
    v = plan([{"do": "action"}], conditions=["Stunned"])
    assert v.exit_code == 1
    assert "condition.stunned.incapacitated" in v.rule_ids


def test_exhaustion_economy_is_a_reasoned_deferral():
    # the one condition deferred on this surface refuses with a NAMED reason
    # (graduated Speed reduction), never the generic "not modeled".
    v = plan([{"do": "action"}], conditions=["Exhaustion"])
    assert v.exit_code == 2
    assert "graduated" in v.why and "not modeled" not in v.why


def test_unknown_step_exit_2():
    assert plan([{"do": "kick-sand"}]).exit_code == 2


def test_two_free_interactions_illegal():
    v = plan([{"do": "free-interaction"}, {"do": "free-interaction"}])
    assert v.exit_code == 1
    assert "turn.one-free-interaction" in v.rule_ids


def test_reaction_available():  # eval ae-05 / ae-06 / ss-01
    ok = E.query("reaction.available", {"spent_since_turn_start": False})
    assert ok.exit_code == 0 and "your own turn" in ok.why
    no = E.query("reaction.available", {"spent_since_turn_start": True})
    assert no.exit_code == 1
    inc = E.query("reaction.available",
                  {"spent_since_turn_start": False,
                   "conditions": ["Incapacitated"]})
    assert inc.exit_code == 1


def test_spent_budgets_carry_in():  # mid-turn queries, not just fresh turns
    v = plan([{"do": "action"}], spent={"action": True})
    assert v.exit_code == 1
    v = plan([{"do": "action", "spell": {"level": 1}}],
             spent={"spell_slots_this_turn": 1})
    assert v.exit_code == 1


def test_all_verdicts_cite():
    cases = [
        plan([{"do": "bonus-action"}, {"do": "bonus-action"}]),
        plan([{"do": "move", "feet": 40}]),
        plan([{"do": "action"}], conditions=["Incapacitated"]),
        plan([{"do": "move", "feet": 10}, {"do": "action"}]),
    ]
    for v in cases:
        assert v.citations, v.why
        assert all(c.quote for c in v.citations), v.why
