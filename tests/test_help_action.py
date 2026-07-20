"""Help action goldens (SRD 5.2.1 p.182-183): the proficiency gate on Assist an
Ability Check, and the 5-ft requirement on Assist an Attack Roll."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def h(**p):
    return E.query("help.assist", p)


def test_assist_ability_check_needs_the_relevant_proficiency():
    ok = h(kind="ability-check", helper_has_relevant_proficiency=True)
    assert ok.exit_code == 0 and ok.data["grants_advantage"] is True
    assert ok.data["gm_discretion"] is True  # surfaced, not adjudicated
    no = h(kind="ability-check", helper_has_relevant_proficiency=False)
    assert no.exit_code == 1
    assert "help.assist-choose-proficiency" in no.rule_ids


def test_assist_attack_roll_needs_an_enemy_within_5ft():
    assert h(kind="attack-roll").exit_code == 0
    assert h(kind="attack-roll", enemy_within_5ft=False).exit_code == 1


def test_unknown_help_kind_refuses():
    assert h(kind="inspire").exit_code == 2
