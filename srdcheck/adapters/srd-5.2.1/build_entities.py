#!/usr/bin/env python3
"""Build entities.json from the extracted SRD text + outline (run after sources/extract.py)."""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
TEXT = ROOT / "sources" / "text"
OUT = pathlib.Path(__file__).parent / "entities.json"

LEVEL_RE = re.compile(
    r"^(Level \d+ \w+|\w+ Cantrip)\b.*\(", re.IGNORECASE)


def spells():
    names = []
    for p in range(105, 175):
        f = TEXT / f"page-{p:03d}.txt"
        if not f.exists():
            continue
        lines = f.read_text().splitlines()
        for i in range(len(lines) - 2):
            name = lines[i].strip()
            if not name or len(name) > 40 or name[0].islower():
                continue
            nxt = lines[i + 1].strip() + " " + lines[i + 2].strip()
            if LEVEL_RE.match(lines[i + 1].strip()) and "Casting Time:" in nxt:
                names.append(name)
    return sorted(set(names))


# Creature stat-block header: "<Size>[ or <Size>] <Type>[ (<subtype>)], <Alignment>"
# e.g. "Small Fey (Goblinoid), Chaotic Neutral", "Medium Swarm of Tiny Beasts,
# Unaligned", "Medium or Small Humanoid, Neutral". The name is the line above it;
# the block carries a "CR <rating> (XP <n>...)" line. Parsed from a continuous
# stream so blocks that span a page break are not lost. This is the source of
# truth for creatures (the PDF outline only bookmarks group headings like
# "Bugbears", missing the individual stat blocks like "Bugbear Warrior").
_SIZE = r"Tiny|Small|Medium|Large|Huge|Gargantuan"
_HEADER = re.compile(
    rf"^({_SIZE})( or ({_SIZE}))? [A-Za-z][A-Za-z ]*?( \([^)]*\))?, ?"
    r"(Lawful|Neutral|Chaotic|Unaligned|Any)", re.IGNORECASE)
_CR = re.compile(r"^CR ([\d/]+) \(XP ([\d,]+)")
_NOISE = re.compile(
    r"^(System Reference Document|\d+\s*$|Monsters|Animals|Traits|Actions|"
    r"Bonus Actions|Reactions|Legendary|Habitats|Treasure)")


def creatures():
    stream = []
    for p in range(257, 365):
        f = TEXT / f"page-{p:03d}.txt"
        if f.exists():
            for line in f.read_text().splitlines():
                stream.append((p, line.rstrip()))
    out = {}
    for i, (page, line) in enumerate(stream):
        if not _HEADER.match(line.strip()):
            continue
        name = None
        for j in range(i - 1, max(i - 4, -1), -1):
            cand = stream[j][1].strip()
            if cand and not _NOISE.match(cand) and not _HEADER.match(cand):
                name = cand
                break
        if not name or len(name) > 45:
            continue
        for k in range(i + 1, min(i + 45, len(stream))):
            if _HEADER.match(stream[k][1].strip()):
                break
            m = _CR.match(stream[k][1].strip())
            if m and name not in out:
                out[name] = {"name": name, "cr": m.group(1),
                             "xp": int(m.group(2).replace(",", "")),
                             "citation": f"SRD 5.2.1 p.{page}"}
                break
    return [out[n] for n in sorted(out)]


def glossary(tag):
    names = set()
    rx = re.compile(rf"^(.{{1,40}}?) \[{tag}\]\s*$")
    for f in sorted(TEXT.glob("page-1*.txt")):
        for line in f.read_text().splitlines():
            m = rx.match(line.strip())
            if m:
                names.add(m.group(1).strip())
    return sorted(names)


def main():
    ents = {
        "spell": spells(),
        "creature": creatures(),
        "condition": glossary("Condition"),
        "action": glossary("Action"),
        "area-of-effect": glossary("Area of Effect"),
    }
    OUT.write_text(json.dumps(ents, indent=1))
    for k, x in ents.items():
        print(f"{k}: {len(x)}", x[:3])


if __name__ == "__main__":
    main()
