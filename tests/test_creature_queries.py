"""creature.valid (#3) and creature.stats (#2)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def valid(name):
    return E.query("creature.valid", {"name": name})


def stats(name):
    return E.query("creature.stats", {"name": name})


def test_valid_creature_is_legal_and_cited():
    v = valid("Goblin Warrior")
    assert v.exit_code == 0
    assert v.citations and v.citations[0].section.startswith("SRD 5.2.1 p.")


def test_case_insensitive():
    assert valid("goblin warrior").exit_code == 0
    assert valid("ABOLETH").exit_code == 0


def test_srd_content_but_not_a_creature_is_illegal():
    v = valid("Fireball")  # a spell
    assert v.exit_code == 1
    assert "not a creature" in v.why


def test_unknown_name_is_cannot_adjudicate():
    # 2014-only name, group heading, and pure nonsense all honestly refuse
    for name in ("Goblin", "Bugbears", "Flumphotron 9000"):
        v = valid(name)
        assert v.exit_code == 2, name


def test_stats_returns_cr_xp_citation():
    v = stats("Ghast")
    assert v.exit_code == 0
    assert v.data == {"name": "Ghast", "cr": "2", "xp": 450,
                      "citation": "SRD 5.2.1 p.287"}
    assert v.citations[0].section == "SRD 5.2.1 p.287"


def test_stats_fractional_cr():
    v = stats("Goblin Minion")
    assert v.data["cr"] == "1/8" and v.data["xp"] == 25


def test_stats_non_creature_refuses():
    assert stats("Fireball").exit_code == 2      # a spell
    assert stats("Definitely Not Real").exit_code == 2
