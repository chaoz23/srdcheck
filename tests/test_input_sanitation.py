"""Launch-hardening regressions (2026-07-17): nonsensical inputs must refuse
(exit 2), never emit a confident-looking verdict; and turn.plan's success
message must state its own scope so 'legal' is never read wider than the
action-economy judgment it actually makes (truths T1, T8)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def test_garbage_inputs_refuse_not_guess():
    assert E.query("turn.plan", {"speed": -30,
                                 "plan": [{"do": "move", "feet": 10}]}
                   ).exit_code == 2
    assert E.query("turn.plan", {"speed": 30,
                                 "plan": [{"do": "action",
                                           "spell": {"level": 99}}]}
                   ).exit_code == 2
    assert E.query("attack.modifiers", {"attacker": {"exhaustion_level": 7},
                                        "target": {}, "distance_ft": 5}
                   ).exit_code == 2
    assert E.query("mage-hand.use", {"kind": "stow_retrieve_open",
                                     "weight_lb": -5, "distance_ft": 10}
                   ).exit_code == 2


def test_valid_boundary_inputs_still_work():
    assert E.query("turn.plan", {"speed": 30,
                                 "plan": [{"do": "action",
                                           "spell": {"level": 9}}]}
                   ).exit_code == 0
    assert E.query("attack.modifiers", {"attacker": {"exhaustion_level": 6},
                                        "target": {}, "distance_ft": 5}
                   ).exit_code == 0
    assert E.query("turn.plan", {"speed": 0, "plan": []}).exit_code == 0


def test_turn_plan_success_states_its_scope():
    """The action-economy legal message must disclaim feature prerequisites,
    so a lone two-weapon-fighting bonus action is never read as fully legal."""
    v = E.query("turn.plan", {"speed": 30, "plan": [{"do": "bonus-action"}]})
    assert v.exit_code == 0
    assert "economy" in v.why.lower()
    assert "does not verify" in v.why.lower()
    assert "feature" in v.why.lower()
