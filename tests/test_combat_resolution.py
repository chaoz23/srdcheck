"""Combat resolution (Measured Engine M1): HP/damage, death saves, saving
throws. The caller supplies every die; the engine folds the consequence, cited
(T2), and never rolls (T6)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])

FRESH_TURN = {"action_spent": False, "bonus_action_spent": False,
              "reaction_spent": False, "free_interaction_spent": False,
              "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0}


def state(**kw):
    base = {"speed": 30, "conditions": [], "concentration_on": None,
            "turn": dict(FRESH_TURN)}
    base.update(kw)
    return base


def apply(st, event):
    v = E.query("event.apply", {"state": st, "event": event})
    return v, (v.data.get("next_state") if v.exit_code == 0 else None)


# --- damage --------------------------------------------------------------

def test_damage_reduces_hp():
    v, s = apply(state(hp=20, hp_max=20), {"type": "damage", "amount": 8})
    assert v.exit_code == 0 and s["hp"] == 12
    assert "damage.reduces-hp" in v.rule_ids


def test_zero_hp_falls_unconscious_and_breaks_concentration():
    st = state(hp=12, hp_max=20, concentration_on="Bless")
    v, s = apply(st, {"type": "damage", "amount": 15})
    assert s["hp"] == 0 and "Unconscious" in s["conditions"]
    assert s["concentration_on"] is None
    assert "hp.falling-unconscious" in v.rule_ids
    assert "concentration.breaks-on-incapacitated" in v.rule_ids


def test_massive_damage_is_instant_death():
    v, s = apply(state(hp=12, hp_max=20), {"type": "damage", "amount": 40})
    assert s["dead"] is True
    assert "hp.massive-damage-death" in v.rule_ids


def test_exactly_to_zero_is_not_massive_damage():
    # remainder 0 < hp_max: unconscious, not dead
    v, s = apply(state(hp=12, hp_max=20), {"type": "damage", "amount": 12})
    assert s["hp"] == 0 and not s.get("dead")
    assert "hp.falling-unconscious" in v.rule_ids


def test_monster_dies_at_zero():
    v, s = apply(state(hp=5, hp_max=30, is_monster=True),
                 {"type": "damage", "amount": 5})
    assert s["dead"] is True
    assert "hp.monster-death" in v.rule_ids


def test_damage_at_zero_is_one_failure():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"])
    v, s = apply(st, {"type": "damage", "amount": 6})
    assert s["death_save_failures"] == 1
    assert "death-save.damage-at-0" in v.rule_ids


def test_crit_at_zero_is_two_failures():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"])
    v, s = apply(st, {"type": "damage", "amount": 6, "crit": True})
    assert s["death_save_failures"] == 2


def test_damage_at_zero_ge_hp_max_is_death():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"])
    v, s = apply(st, {"type": "damage", "amount": 20})
    assert s["dead"] is True


def test_third_failure_from_damage_kills():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"],
               death_save_failures=2)
    v, s = apply(st, {"type": "damage", "amount": 3})
    assert s["death_save_failures"] == 3 and s["dead"] is True


def test_damage_needs_hp_in_state():
    v, _ = apply(state(), {"type": "damage", "amount": 5})
    assert v.exit_code == 2


def test_damage_to_a_dead_creature_is_a_noop():
    v, s = apply(state(hp=0, hp_max=20, dead=True),
                 {"type": "damage", "amount": 5})
    assert v.exit_code == 0 and s["dead"] is True


# --- heal ----------------------------------------------------------------

def test_heal_restores_hp_capped_at_max():
    v, s = apply(state(hp=18, hp_max=20), {"type": "heal", "amount": 10})
    assert s["hp"] == 20
    assert "hp.healing-restores" in v.rule_ids


def test_heal_from_zero_restores_consciousness_and_resets_saves():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"],
               death_save_failures=2, death_save_successes=1)
    v, s = apply(st, {"type": "heal", "amount": 5})
    assert s["hp"] == 5 and "Unconscious" not in s["conditions"]
    assert s["death_save_failures"] == 0 and s["death_save_successes"] == 0
    assert "death-save.reset-on-heal" in v.rule_ids


def test_heal_a_dead_creature_is_illegal():
    v, _ = apply(state(hp=0, hp_max=20, dead=True), {"type": "heal", "amount": 5})
    assert v.exit_code == 1


# --- death saves ---------------------------------------------------------

def test_death_save_success_and_failure_counts():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"])
    _, s = apply(st, {"type": "death-save", "result": 12})
    assert s["death_save_successes"] == 1
    _, s2 = apply(st, {"type": "death-save", "result": 9})
    assert s2["death_save_failures"] == 1


def test_death_save_nat_20_revives():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"], death_save_failures=2)
    v, s = apply(st, {"type": "death-save", "result": 20})
    assert s["hp"] == 1 and s["death_save_failures"] == 0
    assert "Unconscious" not in s["conditions"]
    assert "death-save.natural-1-and-20" in v.rule_ids


def test_death_save_nat_1_is_two_failures():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"], death_save_failures=1)
    v, s = apply(st, {"type": "death-save", "result": 1})
    assert s["death_save_failures"] == 3 and s["dead"] is True


def test_third_success_stabilizes():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"],
               death_save_successes=2)
    _, s = apply(st, {"type": "death-save", "result": 15})
    assert s["stable"] is True and s["death_save_successes"] == 3


def test_third_failure_dies():
    st = state(hp=0, hp_max=20, conditions=["Unconscious"],
               death_save_failures=2)
    _, s = apply(st, {"type": "death-save", "result": 5})
    assert s["dead"] is True


def test_death_save_only_when_unstable_at_zero():
    v, _ = apply(state(hp=10, hp_max=20), {"type": "death-save", "result": 15})
    assert v.exit_code == 2
    v2, _ = apply(state(hp=0, hp_max=20, stable=True),
                  {"type": "death-save", "result": 15})
    assert v2.exit_code == 2


def test_death_save_needs_a_valid_d20():
    v, _ = apply(state(hp=0, hp_max=20, conditions=["Unconscious"]),
                 {"type": "death-save", "result": 0})
    assert v.exit_code == 2


# --- saving throws (stateless queries) -----------------------------------

def test_save_meets_or_exceeds_dc():
    v = E.query("save.check", {"d20_result": 14, "modifier": 3, "dc": 17})
    assert v.exit_code == 0 and v.data["success"] is True  # 17 == DC
    v2 = E.query("save.check", {"d20_result": 13, "modifier": 3, "dc": 17})
    assert v2.data["success"] is False


def test_save_refuses_without_dc():
    assert E.query("save.check", {"d20_result": 10}).exit_code == 2


def test_save_without_roll_reports_the_mode():
    # no d20 supplied: compose and report the roll mode (like attack.modifiers),
    # rather than refuse.
    r = E.query("save.check", {"dc": 10})
    assert r.exit_code == 0 and r.data["roll"] == "straight"


def test_paralyzed_petrified_stunned_unconscious_auto_fail_str_dex():
    for cond in ("Paralyzed", "Petrified", "Stunned", "Unconscious"):
        for ab in ("str", "dex"):
            r = E.query("save.check", {"save_ability": ab,
                                       "saver_conditions": [cond],
                                       "dc": 10, "d20_result": 20})
            assert r.data["success"] is False and r.data["auto_fail"], (cond, ab)
        # a nat-20 CON save is unaffected
        con = E.query("save.check", {"save_ability": "con",
                                     "saver_conditions": [cond],
                                     "dc": 10, "d20_result": 20})
        assert con.data["success"] is True, cond


def test_restrained_disadvantage_on_dex_saves_only():
    dex = E.query("save.check", {"save_ability": "dex",
                                 "saver_conditions": ["Restrained"], "dc": 12})
    assert dex.data["roll"] == "disadvantage"
    con = E.query("save.check", {"save_ability": "con",
                                 "saver_conditions": ["Restrained"], "dc": 12})
    assert con.data["roll"] == "straight"


def test_exhaustion_flat_penalty_on_saves():
    r = E.query("save.check", {"save_ability": "con", "exhaustion_level": 3,
                               "dc": 12, "d20_result": 16})
    assert r.data["total"] == 10 and r.data["success"] is False  # 16 - 6


def test_save_never_rolls():
    # a d20 out of range is a caller error, not something srdcheck fabricates
    assert E.query("save.check", {"d20_result": 25, "dc": 10}).exit_code == 2


def test_concentration_dc_is_half_damage_floor_10_cap_30():
    assert E.query("concentration.check", {"damage": 25}).data["dc"] == 12
    assert E.query("concentration.check", {"damage": 8}).data["dc"] == 10
    assert E.query("concentration.check", {"damage": 100}).data["dc"] == 30


def test_concentration_resolves_when_roll_supplied():
    hold = E.query("concentration.check",
                   {"damage": 25, "d20_result": 12, "con_modifier": 2})
    assert hold.data["success"] is True   # 14 >= 12
    brk = E.query("concentration.check",
                  {"damage": 25, "d20_result": 5, "con_modifier": 2})
    assert brk.data["success"] is False
