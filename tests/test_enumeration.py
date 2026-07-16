"""turn.options — and the T5 consistency property: validation is a
membership check on enumeration. For every state in a sweep, every
single-step plan turn.plan accepts must appear in turn.options, and
everything turn.options offers must pass turn.plan."""

import itertools
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def options(**state):
    return E.query("turn.options", {"speed": 30, **state})


def opt_kinds(verdict):
    return {o["do"] for o in verdict.data["options"]}


def test_fresh_turn_options():
    v = options()
    assert v.exit_code == 0
    assert opt_kinds(v) == {"action", "bonus-action", "reaction",
                            "free-interaction", "move"}
    move = next(o for o in v.data["options"] if o["do"] == "move")
    assert move == {"do": "move", "mode": "walk", "feet_remaining": 30}


def test_prone_options():
    v = options(conditions=["Prone"])
    kinds = opt_kinds(v)
    assert "stand-up" in kinds
    move = next(o for o in v.data["options"] if o["do"] == "move")
    assert move["mode"] == "crawl" and move["feet_remaining"] == 15
    stand = next(o for o in v.data["options"] if o["do"] == "stand-up")
    assert stand["cost_ft"] == 15


def test_prone_grappled_options():
    v = options(conditions=["Prone", "Grappled"])
    kinds = opt_kinds(v)
    assert "move" not in kinds and "stand-up" not in kinds
    assert "cannot right yourself" in v.why


def test_incapacitated_can_still_move():
    v = options(conditions=["Incapacitated"])
    kinds = opt_kinds(v)
    assert kinds == {"free-interaction", "move"}
    assert "movement is not blocked" in v.why


def test_spent_budgets_shrink_options():
    v = options(spent={"action": True, "reaction": True,
                       "free_interaction": True, "movement_ft": 30})
    assert opt_kinds(v) == {"bonus-action"}


def test_slot_flag_follows_spent():
    v = options(spent={"spell_slots_this_turn": 1})
    for o in v.data["options"]:
        if o["do"] in ("action", "bonus-action", "reaction"):
            assert o["spell_slot_available"] is False


def test_unmodeled_condition_exit_2():
    assert options(conditions=["Stunned"]).exit_code == 2


def _single_steps(opts_verdict):
    """Candidate single-step plans implied by an options payload, plus
    probes just past each boundary (must be rejected by turn.plan)."""
    inside, outside = [], []
    kinds = {o["do"]: o for o in opts_verdict.data["options"]}
    for do in ("action", "bonus-action", "reaction", "free-interaction"):
        (inside if do in kinds else outside).append({"do": do})
    if "move" in kinds:
        o = kinds["move"]
        crawl = o["mode"] == "crawl"
        inside.append({"do": "move", "feet": o["feet_remaining"], "crawl": crawl})
        outside.append({"do": "move", "feet": o["feet_remaining"] + 1,
                        "crawl": crawl})
    else:
        outside.append({"do": "move", "feet": 1})
        outside.append({"do": "move", "feet": 1, "crawl": True})
    if "stand-up" in kinds:
        inside.append({"do": "stand-up"})
    else:
        outside.append({"do": "stand-up"})
    return inside, outside


def test_t5_consistency_sweep():
    cond_sets = ([], ["Prone"], ["Grappled"], ["Prone", "Grappled"],
                 ["Incapacitated"])
    spent_sets = [{}, {"action": True}, {"bonus_action": True, "reaction": True},
                  {"movement_ft": 20}, {"free_interaction": True,
                                        "movement_ft": 30}]
    for conds, spent, speed in itertools.product(
            cond_sets, spent_sets, (30, 25)):
        state = {"speed": speed, "conditions": conds, "spent": spent}
        ov = E.query("turn.options", state)
        assert ov.exit_code == 0, (state, ov.why)
        inside, outside = _single_steps(ov)
        for step in inside:
            pv = E.query("turn.plan", {**state, "plan": [step]})
            assert pv.exit_code == 0, ("enumerated but rejected",
                                       state, step, pv.why)
        for step in outside:
            pv = E.query("turn.plan", {**state, "plan": [step]})
            assert pv.exit_code != 0, ("not enumerated but accepted",
                                       state, step)
