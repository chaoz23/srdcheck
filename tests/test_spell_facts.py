"""v0.4 spell facts. Origin: a 10-minute ward narrated active ~70 minutes,
caught by the HUMAN (rule 67, 2026-07-27)."""
import pytest
from srdcheck.engine import Engine
from srdcheck.access import default_adapter_paths


@pytest.fixture(scope="module")
def eng():
    return Engine(default_adapter_paths())


def test_ward_regression(eng):
    v = eng.query("spell.facts", {"name": "Protection from Evil and Good",
                                  "cast_at": 1000.0})
    assert v.exit_code == 0
    f = v.data["facts"]
    assert f["concentration"] is True
    assert "10 minute" in f["duration"].lower()
    assert v.data["expires_at"] == 1000.0 + 600


def test_mage_hand_not_concentration(eng):
    v = eng.query("spell.facts", {"name": "Mage Hand"})
    assert v.data["facts"]["concentration"] is False
    assert "1 minute" in v.data["facts"]["duration"].lower()


def test_unknown_name_refuses(eng):
    assert eng.query("spell.facts", {"name": "Hexblade's Doom"}).exit_code == 2


def test_instantaneous_has_no_expiry(eng):
    v = eng.query("spell.facts", {"name": "Fireball", "cast_at": 5.0})
    assert v.data["expires_at"] is None


def test_divine_sense_blanks(eng):
    v = eng.query("feature.uses", {"feature": "divine-sense"})
    assert "uses" not in v.data and "Charisma" in v.data["formula"]
    v2 = eng.query("feature.uses", {"feature": "divine-sense",
                                    "charisma_modifier": 4})
    assert v2.data["uses"] == 5


def test_census_registry_complete(eng):
    import json, pathlib
    root = pathlib.Path("srdcheck/adapters/srd-5.2.1")
    facts = json.load(open(root / "spell_facts.json"))
    spells = json.load(open(root / "entities.json"))["spell"]
    assert len(facts) == len(spells)   # completeness oracle holds in CI
