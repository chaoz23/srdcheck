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
    assert g(kind="grapple", str_modifier=3, proficiency_bonus=2).data["dc"] == 13
    assert g(kind="shove", str_modifier=4, proficiency_bonus=3).data["dc"] == 15


def test_target_more_than_one_size_larger_is_impossible():
    v = g(kind="grapple", attacker_size="medium", target_size="huge")
    assert v.exit_code == 1 and "unarmed-strike.grapple" in v.rule_ids
    # exactly one size larger is allowed
    assert g(kind="grapple", attacker_size="medium",
             target_size="large").exit_code == 0


def test_grapple_requires_a_free_hand():
    assert g(kind="grapple", has_free_hand=False).exit_code == 1
    # shove has no free-hand requirement
    assert g(kind="shove", has_free_hand=False).exit_code == 0


def test_on_fail_effect_differs_by_kind():
    assert "Grappled" in g(kind="grapple").data["on_fail"]
    assert "Prone" in g(kind="shove").data["on_fail"]


def test_unknown_kind_refuses():
    assert g(kind="trip").exit_code == 2
