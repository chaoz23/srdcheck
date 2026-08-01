"""Grapple / Shove initiation goldens (SRD 5.2.1 p.190, Unarmed Strike)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def g(**p):
    return E.query("grapple.initiate", p)


def test_dc_is_8_plus_str_plus_pb():
    assert g(kind="grapple", str_modifier=3, proficiency_bonus=2,
             attacker_size="medium", target_size="medium",
             has_free_hand=True).data["dc"] == 13
    assert g(kind="shove", str_modifier=4, proficiency_bonus=3,
             attacker_size="medium", target_size="medium").data["dc"] == 15


def test_target_more_than_one_size_larger_is_impossible():
    v = g(kind="grapple", attacker_size="medium", target_size="huge",
          has_free_hand=True)
    assert v.exit_code == 1 and "unarmed-strike.grapple" in v.rule_ids
    # exactly one size larger is allowed
    assert g(kind="grapple", attacker_size="medium",
             target_size="large", has_free_hand=True).exit_code == 0


def test_grapple_requires_a_free_hand():
    assert g(kind="grapple", attacker_size="medium", target_size="medium",
             has_free_hand=False).exit_code == 1
    # shove has no free-hand requirement
    assert g(kind="shove", attacker_size="medium", target_size="medium",
             has_free_hand=False).exit_code == 0


def test_on_fail_effect_differs_by_kind():
    assert "Grappled" in g(
        kind="grapple", attacker_size="medium", target_size="medium",
        has_free_hand=True).data["on_fail"]
    assert "Prone" in g(
        kind="shove", attacker_size="medium", target_size="medium").data["on_fail"]


def test_missing_prerequisite_facts_refuse_instead_of_defaulting_medium_or_free():
    assert g(kind="grapple").exit_code == 2
    assert g(kind="grapple", attacker_size="medium",
             target_size="medium").exit_code == 2
    assert g(kind="shove").exit_code == 2


def test_unknown_kind_refuses():
    assert g(kind="trip").exit_code == 2
