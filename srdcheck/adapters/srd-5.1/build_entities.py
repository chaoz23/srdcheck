#!/usr/bin/env python3
"""Build entities.json for the SRD 5.1 (2014) adapter.

Version-specific: 2014 formatting differs from 2024 (creature stats are
"Challenge X (Y XP)" not "CR X (XP Y; PB +Z)"; types/alignment are lowercase;
the 5.1 PDF extracts with tab/CR/nbsp noise between words). This is the
version-migration seam — a new SRD version needs its own build script emitting
the standard adapter files; the kernel and consumers are untouched.

Run: python srdcheck/adapters/srd-5.1/build_entities.py  (needs the pinned PDF)
"""

import json
import pathlib
import re

HERE = pathlib.Path(__file__).parent
PDF = HERE / "sources" / "SRD_CC_v5.1.pdf"
OUT = HERE / "entities.json"

SIZE = r"(Tiny|Small|Medium|Large|Huge|Gargantuan)"
_HDR = re.compile(
    rf"^{SIZE} (aberration|beast|celestial|construct|dragon|elemental|fey|"
    r"fiend|giant|humanoid|monstrosity|ooze|plant|undead|swarm)", re.I)
_CH = re.compile(r"Challenge ([\d/]+) \(([\d,]+) XP\)")
_SPELL = re.compile(r"^(\d+(st|nd|rd|th)-level \w+|\w+ cantrip)\b", re.I)
_COND = re.compile(r"^(Blinded|Charmed|Deafened|Exhaustion|Frightened|Grappled|"
                   r"Incapacitated|Invisible|Paralyzed|Petrified|Poisoned|Prone|"
                   r"Restrained|Stunned|Unconscious)$")


def _stream():
    from pypdf import PdfReader
    stream = []
    for pg, page in enumerate(PdfReader(PDF).pages, 1):
        t = (page.extract_text() or "").replace("\t", " ").replace("\r", " ")
        # 2014 extraction noise: nbsp, soft hyphen, and Unicode hyphen variants
        # (e.g. the spell level line "1st-<soft><U+2010><U+2011>level").
        t = t.replace("\xa0", " ").replace("\xad", "")
        t = t.replace("‐", "-").replace("‑", "-")
        t = re.sub(r"-{2,}", "-", t)
        for line in re.sub(r" +", " ", t).split("\n"):
            stream.append((pg, line.strip()))
    return stream


def _name_above(stream, i):
    for j in range(i - 1, max(i - 3, -1), -1):
        c = stream[j][1]
        if c and c[0].isupper() and len(c) < 40 and "System Reference" not in c:
            return c
    return None


def creatures(stream):
    out = {}
    for i, (pg, line) in enumerate(stream):
        if not _HDR.match(line):
            continue
        # confirm a stat block (filters lowercase-type false positives in prose)
        if not any("Armor Class" in stream[k][1]
                   for k in range(i + 1, min(i + 4, len(stream)))):
            continue
        name = _name_above(stream, i)
        if not name:
            continue
        for k in range(i + 1, min(i + 50, len(stream))):
            m = _CH.search(stream[k][1])
            if m and name not in out:
                out[name] = {"name": name, "cr": m.group(1),
                             "xp": int(m.group(2).replace(",", "")),
                             "citation": f"SRD 5.1 p.{pg}"}
                break
    return [out[n] for n in sorted(out)]


def spells(stream):
    out = set()
    for i, (pg, line) in enumerate(stream):
        if not _SPELL.match(line):
            continue
        if not any("Casting Time:" in stream[k][1]
                   for k in range(i + 1, min(i + 3, len(stream)))):
            continue
        name = _name_above(stream, i)
        if name and not name[0].islower():
            out.add(name)
    return sorted(out)


def conditions(stream):
    return sorted({line for _, line in stream if _COND.match(line)})


def main():
    stream = _stream()
    ents = {
        "spell": spells(stream),
        "creature": creatures(stream),
        "condition": conditions(stream),
    }
    OUT.write_text(json.dumps(ents, indent=1))
    for k, x in ents.items():
        print(f"{k}: {len(x)}", (x[:2] if x else []))


if __name__ == "__main__":
    main()
