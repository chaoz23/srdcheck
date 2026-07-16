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


def monsters():
    idx = json.loads((ROOT / "sources" / "index.json").read_text())
    return sorted({e["title"] for e in idx
                   if e["page"] and 257 <= e["page"] < 364 and e["depth"] == 2
                   and e["title"] not in ("Monsters A–Z", "Animals")})


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
        "creature": monsters(),
        "condition": glossary("Condition"),
        "action": glossary("Action"),
        "area-of-effect": glossary("Area of Effect"),
    }
    OUT.write_text(json.dumps(ents, indent=1))
    for k, x in ents.items():
        print(f"{k}: {len(x)}", x[:3])


if __name__ == "__main__":
    main()
