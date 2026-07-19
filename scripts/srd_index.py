#!/usr/bin/env python3
"""Parallel SRD index — search the 2024 (srd-5.2.1) and 2014 (srd-5.1) source
text side by side.

The intermediary artifact for building and QC'ing citations: instead of
reconstructing a quote from memory (which is how paraphrased and mis-paged
citations slipped in), look it up directly and copy the verbatim text + page.

    # find a phrase in both editions (verbatim, whitespace/hyphen-insensitive)
    python scripts/srd_index.py "you can expend only one spell slot"

    # QC every srd-5.2.1 atom quote by edition: present in 2024? 2014? which pages?
    python scripts/srd_index.py --audit

Text is derived from each adapter's pinned PDF by its sources/extract.py; run
that first if an edition reports no pages.
"""

import argparse
import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "srdcheck" / "adapters"
EDITIONS = {"2024": "srd-5.2.1", "2014": "srd-5.1"}


def squash(s):
    s = unicodedata.normalize("NFKC", s)
    for a, b in [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("…", "...")]:
        s = s.replace(a, b)
    return re.sub(r"[\s\-‐‑–—]+", "", s).lower()


def load(edition):
    """Return {page: (raw_text, squashed_text)} for an edition, or {} if not
    extracted yet."""
    tdir = ADAPTERS / EDITIONS[edition] / "sources" / "text"
    out = {}
    for p in sorted(tdir.glob("page-*.txt")):
        raw = p.read_text()
        out[int(re.search(r"(\d+)", p.stem).group(1))] = (raw, squash(raw))
    return out


def find(phrase, corpus):
    """Pages of `corpus` whose squashed text contains the squashed phrase."""
    sq = squash(phrase)
    return sorted(pg for pg, (_, t) in corpus.items() if sq in t)


def _context(raw, phrase, width=90):
    # locate the phrase loosely (first significant word) for a readable snippet
    words = [w for w in re.findall(r"\w+", phrase) if len(w) > 3]
    if not words:
        return ""
    i = raw.lower().find(words[0].lower())
    if i < 0:
        return ""
    seg = re.sub(r"\s+", " ", raw[max(0, i - 20):i + width]).strip()
    return seg


def cmd_search(phrase):
    any_hit = False
    for ed in EDITIONS:
        corpus = load(ed)
        if not corpus:
            print(f"  {ed}: (no text — run {EDITIONS[ed]}/sources/extract.py)")
            continue
        pages = find(phrase, corpus)
        if pages:
            any_hit = True
            for pg in pages:
                print(f"  {ed} p.{pg}: …{_context(corpus[pg][0], phrase)}…")
        else:
            print(f"  {ed}: not found")
    return 0 if any_hit else 1


def _atoms(edition):
    for f in (ADAPTERS / EDITIONS[edition] / "atoms").glob("*.json"):
        for atom in json.loads(f.read_text()):
            if atom.get("citation", {}).get("quote"):
                yield atom


def cmd_audit():
    """Every srd-5.2.1 atom quote, classified by edition presence."""
    c24, c14 = load("2024"), load("2014")
    if not c24 or not c14:
        sys.exit("Both editions must be extracted first (run each "
                 "sources/extract.py).")
    rows, shared, only24, missing = [], 0, 0, 0
    for atom in sorted(_atoms("2024"), key=lambda a: a["id"]):
        q = atom["citation"]["quote"]
        cited = atom["citation"].get("page")
        p24, p14 = find(q, c24), find(q, c14)
        tag = ("MISSING-2024" if not p24
               else "shared" if p14 else "2024-only")
        if not p24:
            missing += 1
        elif p14:
            shared += 1
        else:
            only24 += 1
        onpage = "" if not p24 else ("" if cited in p24 else f"  !CITED p.{cited}")
        rows.append(f"  {tag:12} {atom['id']:34} 2024={p24 or '—'} 2014={p14 or '—'}{onpage}")
    print("\n".join(rows))
    print(f"\n{shared} shared with 2014 · {only24} 2024-only · {missing} "
          f"missing-from-2024 (should be 0)")
    return 1 if missing else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phrase", nargs="?", help="phrase to find in both editions")
    ap.add_argument("--audit", action="store_true",
                    help="classify every srd-5.2.1 atom quote by edition")
    args = ap.parse_args()
    if args.audit:
        sys.exit(cmd_audit())
    if not args.phrase:
        ap.error("give a phrase to search, or --audit")
    sys.exit(cmd_search(args.phrase))


if __name__ == "__main__":
    main()
