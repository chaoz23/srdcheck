"""Ability-check surface goldens (deferred-work pass): condition-aware D20 Tests."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def check(**p):
    return E.query("check.make", p)


def test_blinded_auto_fails_sight_checks_only():
    sight = check(actor_conditions=["Blinded"], check_requires="sight",
                  dc=5, d20_result=20)
    assert sight.data["success"] is False and sight.data["auto_fail"]
    # a check that doesn't require sight resolves normally
    other = check(actor_conditions=["Blinded"], dc=5, d20_result=20)
    assert other.data["success"] is True


def test_deafened_auto_fails_hearing_checks():
    r = check(actor_conditions=["Deafened"], check_requires="hearing",
              dc=5, d20_result=20)
    assert r.data["success"] is False and r.data["auto_fail"]
    assert "condition.deafened.cant-hear" in r.rule_ids


def test_poisoned_and_frightened_impose_disadvantage_on_checks():
    assert check(actor_conditions=["Poisoned"], dc=10).data["roll"] == "disadvantage"
    assert check(actor_conditions=["Frightened"], dc=10).data["roll"] == "disadvantage"


def test_charmer_has_advantage_on_social_checks():
    r = check(target_charmed_by_actor=True, social=True, dc=10)
    assert r.data["roll"] == "advantage"
    assert "condition.charmed.social-advantage" in r.rule_ids
    # not a social check: no advantage
    assert check(target_charmed_by_actor=True, dc=10).data["roll"] == "straight"


def test_exhaustion_penalty_on_checks():
    r = check(exhaustion_level=2, dc=12, d20_result=15)
    assert r.data["total"] == 11 and r.data["success"] is False  # 15 - 4


def test_check_refuses_without_dc():
    assert check(d20_result=10).exit_code == 2
