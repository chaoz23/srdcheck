#!/usr/bin/env python3
"""Build spell_facts.json from the SRD page text. Completeness oracle: every
registered spell must yield casting_time, range, components and duration, or
the build FAILS loudly (extraction-completeness pattern - no silent misses)."""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "srdcheck/adapters/srd-5.2.1"
ents = json.load(open(ROOT / "entities.json"))
spells = ents["spell"]
pages = {int(p.stem.split("-")[1]): p.read_text()
         for p in sorted((ROOT / "sources/text").glob("page-*.txt"))}

F = re.compile(r"Casting Time:\s*(?P<ct>[^\n]+)\n.*?Range:\s*(?P<rg>[^\n]+)\n"
               r".*?Components?:\s*(?P<cp>[^\n]+)\n.*?Duration:\s*(?P<du>[^\n]+)", re.S)
LVL = re.compile(r"(?:Level (\d+) )?(\w+)(?: Cantrip)?", re.I)

out, misses = {}, []
for name in spells:
    pat = re.compile(rf"^{re.escape(name)}\s*$", re.M | re.I)
    rec = None
    for pg in sorted(pages):
        m = pat.search(pages[pg])
        if not m:
            continue
        block = pages[pg][m.start():m.start() + 1200]
        # spill to next page when the stat lines cross a page break
        if "Duration:" not in block and pg + 1 in pages:
            block += "\n" + pages[pg + 1][:600]
        g = F.search(block)
        if not g:
            continue
        du = g["du"].strip()
        rec = {"casting_time": g["ct"].strip(), "range": g["rg"].strip(),
               "components": g["cp"].strip(), "duration": du,
               "concentration": du.lower().startswith("concentration"),
               "page": pg}
        break
    if rec:
        out[name.lower()] = rec
    else:
        misses.append(name)

if misses:
    print(f"FAIL: {len(misses)} spells without complete facts: {misses[:12]}",
          file=sys.stderr)
    sys.exit(1)
json.dump(out, open(ROOT / "spell_facts.json", "w"), indent=0, sort_keys=True)
print(f"OK: {len(out)}/{len(spells)} spells with complete facts")
