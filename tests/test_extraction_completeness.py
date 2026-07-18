"""Completeness oracles (issue #6): cross-check each bulk-extracted category's
registry size against an INDEPENDENT anchor in the SRD text, so a heuristic that
silently drops entries becomes a build failure instead of an invisible
false-refusal. This is the guard that would have caught both the creature
incompleteness (#1) and the spell incompleteness (#6) at ship time.

Requires the extracted SRD text (CI runs sources/extract.py first); skipped on a
fresh checkout that hasn't fetched + extracted the PDF."""

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEXT = ROOT / "sources" / "text"
REG = json.loads(
    (ROOT / "srdcheck" / "adapters" / "srd-5.2.1" / "entities.json").read_text())

pytestmark = pytest.mark.skipif(
    not (TEXT / "page-105.txt").exists(),
    reason="SRD text not extracted (run sources/fetch.sh && sources/extract.py)")


def _count(pattern, lo, hi):
    n = 0
    for p in range(lo, hi):
        f = TEXT / f"page-{p:03d}.txt"
        if f.exists():
            n += len(re.findall(pattern, f.read_text(), re.M))
    return n


def test_spell_registry_is_complete():
    # every spell description has exactly one "Casting Time:" line
    anchors = _count(r"^Casting Time:", 105, 175)
    assert len(REG["spell"]) == anchors, (
        f"registry has {len(REG['spell'])} spells but the text has {anchors} "
        "spell blocks — the extractor is dropping (or duplicating) entries")


def test_creature_registry_is_complete():
    # every creature stat block has exactly one "CR X (XP Y)" line
    anchors = _count(r"^CR [\d/]+ \(XP", 257, 365)
    assert len(REG["creature"]) == anchors, (
        f"registry has {len(REG['creature'])} creatures but the text has "
        f"{anchors} stat blocks")


def test_conditions_match_the_enumerated_glossary_list():
    p179 = (TEXT / "page-179.txt").read_text()
    m = re.search(r"defines these conditions:\s*(.*?)\s*A condition doesn",
                  p179, re.S)
    listed = [x.strip() for x in m.group(1).splitlines() if x.strip()]
    assert sorted(REG["condition"]) == sorted(listed)


def test_no_casing_artifacts_in_spell_names():
    # 'SplASh'-style pypdf glitches: a lowercase immediately followed by uppercase
    bad = [s for s in REG["spell"] if re.search(r"[a-z][A-Z]", s)]
    assert not bad, f"casing artifacts in spell names: {bad}"
