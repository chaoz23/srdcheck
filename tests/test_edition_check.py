"""edition_check — cross-version edition-trap detection (Version Layer M2).

The deferred bonus from issue #3, now earned by having both SRD versions:
a name in a prior version but not the current one is an edition trap."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import srdcheck  # noqa: E402
from srdcheck.access import edition_check  # noqa: E402


def test_2014_creature_name_is_an_edition_trap():
    v = edition_check("Goblin", "creature")
    assert v.exit_code == 1
    assert v.data["edition_trap"] and v.data["found_in"] == "srd-5.1"
    assert v.citations[0].section == "SRD 5.1 p.315"
    # suggests the 5.2.1 replacements
    assert "Goblin Warrior" in v.data["candidates_in_current"]


def test_valid_current_creature_is_legal():
    assert edition_check("Aboleth", "creature").exit_code == 0       # in both
    assert edition_check("Goblin Warrior", "creature").exit_code == 0  # 5.2.1


def test_unknown_is_cannot_adjudicate():
    v = edition_check("Flumphotron 9000", "creature")
    assert v.exit_code == 2 and not v.data.get("edition_trap")


def test_works_for_spells_too():
    assert edition_check("Cure Wounds", "spell").exit_code == 0   # in both
    assert edition_check("Fire Bolt", "spell").exit_code == 0


def test_case_insensitive():
    assert edition_check("goblin", "creature").exit_code == 1


def test_exported_at_top_level():
    assert srdcheck.edition_check is edition_check


def test_content_neutral_signature():
    # category and versions are parameters — nothing game-specific is hardcoded
    v = edition_check("X", "creature", current="srd-5.2.1", priors=("srd-5.1",))
    assert v.exit_code in (0, 1, 2)


def test_cli_edition_check():
    def run(*a):
        return subprocess.run([sys.executable, "-m", "srdcheck", *a],
                              capture_output=True, text=True, cwd=ROOT)
    r = run("edition-check", "Goblin", "--category", "creature")
    assert r.returncode == 1
    assert json.loads(r.stdout)["data"]["edition_trap"] is True
    assert run("edition-check", "Aboleth").returncode == 0
