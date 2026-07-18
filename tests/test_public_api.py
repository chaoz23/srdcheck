"""Stable public interface (#5): load_adapter + AdapterHandle, version-aware,
content-neutral, decoupled from internal file paths."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import srdcheck  # noqa: E402


def test_top_level_exports():
    assert hasattr(srdcheck, "load_adapter")
    assert hasattr(srdcheck, "available_adapters")


def test_available_adapters_lists_versioned_ids():
    ids = srdcheck.available_adapters()
    assert "srd-5.2.1" in ids and "toy-tictactoe" in ids


def test_load_and_provenance():
    a = srdcheck.load_adapter("srd-5.2.1")
    assert a.name == "srd-5.2.1"
    assert a.version and a.manifest["license"] == "CC-BY-4.0"


def test_unknown_adapter_raises_helpfully():
    try:
        srdcheck.load_adapter("srd-9.9.9")
    except ValueError as e:
        assert "available" in str(e)
    else:
        assert False, "expected ValueError"


def test_generic_category_access():
    a = srdcheck.load_adapter("srd-5.2.1")
    cats = a.categories()
    assert {"creature", "spell", "condition"} <= set(cats)
    names = a.names("creature")
    assert "Goblin Warrior" in names and len(names) >= 320


def test_record_access_and_query_bridge():
    a = srdcheck.load_adapter("srd-5.2.1")
    rec = a.record("creature", "ghast")  # case-insensitive
    assert rec["cr"] == "2" and rec["xp"] == 450
    # query through the supported surface, no internal-path coupling
    v = a.query("creature.stats", {"name": "Ghast"})
    assert v["exit_code"] == 0 and v["data"]["xp"] == 450


def test_version_aware_isolation():
    # a second (hypothetical) SRD version would load as its own identifier;
    # the toy adapter stands in to prove identifiers are independent handles
    toy = srdcheck.load_adapter("toy-tictactoe")
    assert toy.id != srdcheck.load_adapter("srd-5.2.1").id
    assert "creature" not in toy.categories()
