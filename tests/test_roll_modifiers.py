"""Modifier composition goldens — several ported from the Phase 0 eval set."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def compose(**p):
    return E.query("roll.compose", p)


def attack(**p):
    return E.query("attack.modifiers", p)


def test_two_adv_one_dis_is_straight():  # eval st-01
    v = compose(advantage_sources=["a", "b"], disadvantage_sources=["c"])
    assert v.data["roll"] == "straight" and v.data["d20s"] == 1
    assert "roll.both-cancel" in v.rule_ids


def test_stacked_advantage_still_two_dice():  # eval st-02
    v = compose(advantage_sources=["a", "b", "c"])
    assert v.data["roll"] == "advantage" and v.data["d20s"] == 2
    assert "roll.dont-stack" in v.rule_ids


def test_reroll_only_one_die():  # eval st-03
    v = compose(advantage_sources=["a"], reroll_available=True)
    assert "roll.reroll-one-die" in v.rule_ids
    assert "one die" in v.data["reroll_note"]


def test_invisible_archer_vs_prone_guard():  # eval ss-06 / doc example 2
    v = attack(attacker={"conditions": ["Invisible"]},
               target={"conditions": ["Prone"]}, distance_ft=20)
    assert v.exit_code == 0
    assert v.data["roll"] == "straight"
    assert len(v.data["advantage_sources"]) == 1
    assert len(v.data["disadvantage_sources"]) == 1


def test_seen_invisible_attacker_loses_advantage():  # eval cn-06
    v = attack(attacker={"conditions": ["Invisible"]},
               target={"conditions": [], "can_see_attacker": True},
               distance_ft=10)
    assert v.data["roll"] == "straight"
    assert v.data["advantage_sources"] == []


def test_prone_target_distance_flip():  # eval cn-02
    near = attack(attacker={}, target={"conditions": ["Prone"]}, distance_ft=5)
    far = attack(attacker={}, target={"conditions": ["Prone"]}, distance_ft=60)
    assert near.data["roll"] == "advantage"
    assert far.data["roll"] == "disadvantage"


def test_paralyzed_and_stunned_targets_grant_advantage():
    for cond in ("Paralyzed", "Stunned"):
        v = attack(attacker={}, target={"conditions": [cond]}, distance_ft=30)
        assert v.data["roll"] == "advantage", cond


def test_grappled_attacker_vs_non_grappler():  # 2024 addition
    v = attack(attacker={"conditions": ["Grappled"]}, target={}, distance_ft=5)
    assert v.data["roll"] == "disadvantage"
    ok = attack(attacker={"conditions": ["Grappled"]},
                target={"is_grappler_of_attacker": True}, distance_ft=5)
    assert ok.data["roll"] == "straight"


def test_exhaustion_is_flat_not_advantage():  # eval cn-04 (edition trap)
    v = attack(attacker={"exhaustion_level": 3}, target={}, distance_ft=5)
    assert v.data["roll"] == "straight"
    assert v.data["flat_modifiers"] == [
        {"value": -6, "source": "Exhaustion level 3"}]


def test_seen_invisible_target_is_ambiguous_exit_2():
    v = attack(attacker={"can_see_target": True},
               target={"conditions": ["Invisible"]}, distance_ft=10)
    assert v.exit_code == 2
    assert "ambiguous" in v.why


def test_unmodeled_condition_exit_2():
    v = attack(attacker={"conditions": ["Frightened"]}, target={},
               distance_ft=5)
    assert v.exit_code == 2
    assert "not modeled" in v.why


def test_all_attack_verdicts_cite():
    v = attack(attacker={"conditions": ["Blinded", "Prone"]},
               target={"conditions": ["Restrained"]}, distance_ft=5)
    assert v.data["roll"] == "straight"
    assert v.citations and all(c.quote for c in v.citations)
