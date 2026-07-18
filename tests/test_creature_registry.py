"""Creature registry: complete stat-block coverage + CR/XP/citation (issue #1).

The registry is parsed from creature stat blocks in the SRD text, not the PDF
outline (which only bookmarks group headings like 'Bugbears' and missed the
individual stat blocks like 'Bugbear Warrior')."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.adapter import Adapter  # noqa: E402

ADAPTER = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"
CREATURES = {c["name"]: c
             for c in json.loads((ADAPTER / "entities.json").read_text())["creature"]}


def test_creatures_are_enriched_records():
    for c in CREATURES.values():
        assert set(c) >= {"name", "cr", "xp", "citation"}, c
        assert c["citation"].startswith("SRD 5.2.1 p."), c
        assert isinstance(c["xp"], int)


def test_completeness_floor():
    # 275 (old, outline-based) was incomplete; stat-block parse recovers 320+.
    assert len(CREATURES) >= 320


def test_known_creature_stats_are_correct():
    assert (CREATURES["Aboleth"]["cr"], CREATURES["Aboleth"]["xp"]) == ("10", 5900)
    assert (CREATURES["Ghast"]["cr"], CREATURES["Ghast"]["xp"]) == ("2", 450)
    assert (CREATURES["Ancient Red Dragon"]["cr"],
            CREATURES["Ancient Red Dragon"]["xp"]) == ("24", 62000)
    # fractional CR
    assert (CREATURES["Goblin Warrior"]["cr"],
            CREATURES["Goblin Warrior"]["xp"]) == ("1/4", 50)


def test_previously_missing_creatures_present():
    for name in ("Goblin Warrior", "Goblin Minion", "Adult Red Dragon",
                 "Swarm of Bats", "Bugbear Warrior", "Chain Devil"):
        assert name in CREATURES, name


def test_group_headings_dropped():
    # plural group headings are not stat-block creatures
    for heading in ("Bugbears", "Black Dragons", "Goblins"):
        assert heading not in CREATURES, heading


def test_adapter_exposes_creature_record():
    a = Adapter(ADAPTER)
    rec = a.entity_record("creature", "goblin warrior")  # case-insensitive
    assert rec and rec["xp"] == 50 and rec["cr"] == "1/4"
    assert a.entity_record("creature", "Not A Creature") is None
