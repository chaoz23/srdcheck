#!/usr/bin/env python3
"""Extract the closed SRD 5.2.1 character-option name sets from the source
page text and merge them into entities.json. Census-anchored: tests compare the
result with independent structural anchors in the pinned source (issues #12/#15).

Backgrounds are registry-only here: this records which named backgrounds exist
in SRD 5.2.1 without interpreting their ability scores, feats, proficiencies,
or equipment.
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADIR = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"
TEXT = ADIR / "sources" / "text"

CLASSES = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin",
           "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard"]
SPECIES = ["Dragonborn", "Dwarf", "Elf", "Gnome", "Goliath", "Halfling",
           "Human", "Orc", "Tiefling"]

def extract():
    pages = {p.name: p.read_text() for p in sorted(TEXT.glob("page-*.txt"))}
    # verify every class/species appears as a standalone heading
    all_text = "\n".join(pages.values())
    for name in CLASSES + SPECIES:
        assert re.search(rf"^{name}\s*$", all_text, re.M), f"heading missing: {name}"

    # Background names: inside the source's "Background Descriptions" section,
    # each named entry is immediately followed by its "Ability Scores:" field.
    # Bound the parse at "Character Species" so later uses of the same field
    # cannot become background names. This intentionally extracts names only;
    # background mechanics are outside this registry-only slice.
    descriptions = all_text.split("Background Descriptions", 1)[1]
    descriptions = descriptions.split("Character Species", 1)[0]
    background_lines = [line.strip() for line in descriptions.splitlines()]
    backgrounds = {
        background_lines[i - 1]
        for i, line in enumerate(background_lines)
        if i and line.startswith("Ability Scores:") and background_lines[i - 1]
    }
    # subclasses: "<Class> Subclass: NAME" (wrap-aware, TOC lines excluded)
    subs = set()
    for t in pages.values():
        lines = t.splitlines()
        for i, l in enumerate(lines):
            m = re.search(r"Subclass:\s*(.*)$", l)
            if not m or "..." in l:
                continue
            name = re.sub(r"\s+", " ", m.group(1)).strip()
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if (not name or name.endswith((" the", " of", " the Open"))
                    or (name in ("Draconic", "Warrior of the") )) and nxt and "..." not in nxt:
                name = re.sub(r"\s+", " ", (name + " " + nxt)).strip()
            if name and "..." not in name and not re.search(r"\d", name):
                subs.add(name)
    subs = {s for s in subs if not any(o != s and o.startswith(s) for o in subs)}
    # feats: heading line immediately followed by "<Category> Feat" or "... Feat ("
    feats = {}
    for t in pages.values():
        lines = [l.strip() for l in t.splitlines()]
        for i, l in enumerate(lines[:-1]):
            m = re.match(r"^(Origin|General|Epic Boon|Fighting Style) Feat( \(|$)", lines[i + 1])
            if m and l and "..." not in l and not l.endswith("Feats") \
                    and len(l) < 40 and l[0].isalpha():
                feats[l] = m.group(1)
    return {"class": sorted(CLASSES), "subclass": sorted(subs),
            "species": sorted(SPECIES), "feat": sorted(feats),
            "background": sorted(backgrounds)}

if __name__ == "__main__":
    sets = extract()
    ents = json.load(open(ADIR / "entities.json"))
    ents.update(sets)
    json.dump(ents, open(ADIR / "entities.json", "w"), indent=1)
    for k, v in sets.items():
        print(f"{k}: {len(v)}")
