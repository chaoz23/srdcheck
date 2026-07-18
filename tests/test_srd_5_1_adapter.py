"""SRD 5.1 (2014) adapter — Version Layer epic M1.

Proves a second SRD *version* loads with zero kernel changes, is complete
(completeness oracle, applying the lesson from the 5.2.1 spell/creature bugs),
carries the bare 2014 names that power edition-trap detection, and does NOT
blur the default 5.2.1 engine."""

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import srdcheck  # noqa: E402
from srdcheck.access import default_adapter_paths  # noqa: E402

ADIR = ROOT / "srdcheck" / "adapters" / "srd-5.1"
REG = json.loads((ADIR / "entities.json").read_text())
PDF = ADIR / "sources" / "SRD_CC_v5.1.pdf"


def test_loads_as_a_versioned_adapter():
    a = srdcheck.load_adapter("srd-5.1")
    assert a.name == "srd-5.1"
    assert a.manifest["license"] == "CC-BY-4.0"
    assert "SRD 5.1" in a.manifest["attribution"]


def test_not_in_the_default_engine():
    # 5.1 is loadable-on-demand but must not blur the primary 5.2.1 engine
    default_names = [p.name for p in default_adapter_paths()]
    assert "srd-5.1" not in default_names
    assert "srd-5.2.1" in default_names


def test_carries_the_2014_edition_trap_names():
    a = srdcheck.load_adapter("srd-5.1")
    creatures = set(a.names("creature"))
    # bare 2014 names that were renamed/removed in 5.2.1
    for name in ("Goblin", "Orc", "Bugbear", "Gnoll", "Hobgoblin"):
        assert name in creatures, name
    rec = a.record("creature", "Goblin")
    assert rec["cr"] == "1/4" and rec["citation"].startswith("SRD 5.1 p.")


def test_registry_shape():
    assert len(REG["creature"]) >= 300
    assert len(REG["spell"]) >= 300
    assert sorted(REG["condition"]) == sorted([
        "Blinded", "Charmed", "Deafened", "Exhaustion", "Frightened",
        "Grappled", "Incapacitated", "Invisible", "Paralyzed", "Petrified",
        "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious"])
    for c in REG["creature"]:
        assert {"name", "cr", "xp", "citation"} <= set(c)


@pytest.mark.skipif(not PDF.exists(), reason="SRD 5.1 PDF not fetched")
def test_completeness_oracle():
    from pypdf import PdfReader
    full = "\n".join((p.extract_text() or "") for p in PdfReader(PDF).pages)
    full = re.sub(r" +", " ", full.replace("\t", " ").replace(
        "\r", " ").replace("\xa0", " "))
    challenge = len(re.findall(r"Challenge [\d/]+ \([\d,]+ XP\)", full))
    casting = len(re.findall(r"\nCasting Time:", full))
    assert len(REG["creature"]) == challenge, (
        f"5.1 creatures {len(REG['creature'])} != {challenge} Challenge anchors")
    assert len(REG["spell"]) == casting, (
        f"5.1 spells {len(REG['spell'])} != {casting} Casting-Time anchors")
