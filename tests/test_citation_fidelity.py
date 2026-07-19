"""Citation fidelity oracle (T2: no citation, no rule).

Every atom's citation.quote must appear VERBATIM in the exact source location it
cites — on the cited page for the SRD adapters, or in RULES.md for the toy
adapter. Matching is whitespace- and hyphen-insensitive and normalizes curly
quotes, to absorb the PDF extraction's soft-wrap line breaks and typography;
beyond that it is a strict contiguous-substring check, so a paraphrased, stitched,
or mis-paged quote fails. This is the guard that makes "cited and verifiable" a
CI guarantee instead of a manual audit."""

import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "srdcheck" / "adapters"


def squash(s):
    s = unicodedata.normalize("NFKC", s)
    for a, b in [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("…", "...")]:
        s = s.replace(a, b)
    return re.sub(r"[\s\-‐‑–—]+", "", s).lower()


def _pages(adapter):
    tdir = adapter / "sources" / "text"
    if not tdir.is_dir():
        return {}
    out = {}
    for p in tdir.glob("page-*.txt"):
        out[int(re.search(r"(\d+)", p.stem).group(1))] = squash(p.read_text())
    return out


def _atoms(adapter):
    for f in (adapter / "atoms").glob("*.json"):
        for atom in json.loads(f.read_text()):
            yield atom


def test_every_atom_quote_is_verbatim_at_its_citation():
    failures = []
    for adapter in sorted(p for p in ADAPTERS.iterdir() if p.is_dir()):
        pages = _pages(adapter)
        rules_md = adapter / "RULES.md"
        rules_sq = squash(rules_md.read_text()) if rules_md.exists() else None
        for atom in _atoms(adapter):
            cite = atom.get("citation") or {}
            quote = cite.get("quote")
            if not quote:
                continue
            sq = squash(quote)
            page = cite.get("page")
            if page is not None and pages:
                if sq in pages.get(page, ""):
                    continue
                elsewhere = sorted(p for p, t in pages.items() if sq in t)
                note = (f"found on page(s) {elsewhere}" if elsewhere
                        else "not found verbatim on any page")
                failures.append(f"{adapter.name}/{atom['id']}: cites p.{page}, "
                                f"{note} — {quote[:55]!r}")
            elif rules_sq is not None:
                if sq not in rules_sq:
                    failures.append(f"{adapter.name}/{atom['id']}: not verbatim "
                                    f"in RULES.md — {quote[:55]!r}")
            else:
                failures.append(f"{adapter.name}/{atom['id']}: no source text to "
                                "verify the citation against")
    assert not failures, "citation fidelity failures:\n  " + "\n  ".join(failures)
