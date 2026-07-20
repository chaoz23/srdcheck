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


def test_unknown_condition_exit_2():
    # every SRD condition is now modeled (see test_condition_completeness); the
    # remaining honest refusal is content that isn't an SRD condition at all.
    v = attack(attacker={"conditions": ["Bewildered"]}, target={},
               distance_ft=5)
    assert v.exit_code == 2
    assert "not a condition known" in v.why


def test_frightened_is_modeled_not_refused():
    v = attack(attacker={"conditions": ["Frightened"]}, target={},
               distance_ft=5)
    assert v.exit_code == 0 and v.data["roll"] == "disadvantage"


def test_all_attack_verdicts_cite():
    v = attack(attacker={"conditions": ["Blinded", "Prone"]},
               target={"conditions": ["Restrained"]}, distance_ft=5)
    assert v.data["roll"] == "straight"
    assert v.citations and all(c.quote for c in v.citations)


# --- condition completeness pass: attack-effect goldens -------------------

def test_poisoned_attacker_has_disadvantage():
    v = attack(attacker={"conditions": ["Poisoned"]}, target={}, distance_ft=5)
    assert v.data["roll"] == "disadvantage"
    assert "condition.poisoned.attacks" in v.rule_ids


def test_frightened_disadvantage_only_when_source_in_sight():
    seen = attack(attacker={"conditions": ["Frightened"]}, target={},
                  distance_ft=5)
    assert seen.data["roll"] == "disadvantage"
    unseen = attack(attacker={"conditions": ["Frightened"],
                              "frightened_source_in_sight": False},
                    target={}, distance_ft=5)
    assert unseen.data["roll"] == "straight"  # cited, but no Disadvantage


def test_charmed_cannot_attack_the_charmer():
    illegal = attack(attacker={"conditions": ["Charmed"]},
                     target={"is_charmer_of_attacker": True}, distance_ft=5)
    assert illegal.exit_code == 1
    assert "condition.charmed.cant-harm-charmer" in illegal.rule_ids
    # against anyone else, Charmed imposes nothing
    other = attack(attacker={"conditions": ["Charmed"]}, target={}, distance_ft=5)
    assert other.exit_code == 0 and other.data["roll"] == "straight"


def test_ranged_in_close_combat_disadvantage_and_exceptions():
    seen = attack(attacker={}, target={}, distance_ft=30, ranged=True,
                  nearby_enemies=[{"can_see_attacker": True, "conditions": []}])
    assert seen.data["roll"] == "disadvantage"
    assert "attack.ranged-in-close-combat" in seen.rule_ids
    # exception: an enemy who can't see you does not impose it
    blind = attack(attacker={}, target={}, distance_ft=30, ranged=True,
                   nearby_enemies=[{"can_see_attacker": False, "conditions": []}])
    assert blind.data["roll"] == "straight"
    # exception: an Incapacitated enemy does not impose it
    incap = attack(attacker={}, target={}, distance_ft=30, ranged=True,
                   nearby_enemies=[{"can_see_attacker": True,
                                    "conditions": ["Incapacitated"]}])
    assert incap.data["roll"] == "straight"
    # a melee attack (ranged not set) is unaffected
    assert attack(attacker={}, target={}, distance_ft=5).data["roll"] == "straight"


def test_target_petrified_and_unconscious_grant_advantage():
    for cond in ("Petrified", "Unconscious"):
        v = attack(attacker={}, target={"conditions": [cond]}, distance_ft=30)
        assert v.data["roll"] == "advantage", cond


def test_unconscious_and_paralyzed_auto_crit_within_5ft():
    for cond in ("Unconscious", "Paralyzed"):
        near = attack(attacker={}, target={"conditions": [cond]}, distance_ft=5)
        assert near.data.get("auto_crit_on_hit"), cond
        far = attack(attacker={}, target={"conditions": [cond]}, distance_ft=30)
        assert not far.data.get("auto_crit_on_hit"), cond
