"""The atom concordance is generated, never hand-edited — CI checks it is fresh
(same discipline as the scorecards). Combined with test_citation_fidelity (every
quote is verbatim at its cited page), this makes the concordance a trustworthy
audit trail: what it shows is exactly what the engine applies, grounded in the
pinned SRD."""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "concordance", ROOT / "scripts" / "concordance.py")
conc = importlib.util.module_from_spec(spec)
sys.modules["concordance"] = conc
spec.loader.exec_module(conc)


def test_concordance_markdown_is_fresh():
    rows = conc._rows()
    on_disk = (ROOT / "docs" / "atom-concordance.md").read_text()
    assert on_disk == conc.build_md(rows), \
        "docs/atom-concordance.md is stale — run scripts/concordance.py"


def test_concordance_json_is_fresh():
    import json
    rows = conc._rows()
    on_disk = (ROOT / "docs" / "atom-concordance.json").read_text()
    fresh = json.dumps(conc.build_json(rows), indent=1, ensure_ascii=False) + "\n"
    assert on_disk == fresh, \
        "docs/atom-concordance.json is stale — run scripts/concordance.py"


def test_concordance_covers_every_cited_atom():
    rows = conc._rows()
    data = conc.build_json(rows)
    # every atom with a quote is in the forward map and in exactly one page group
    for r in rows:
        assert r["atom"] in data["atoms"], r["atom"]
    placed = [a for atoms in data["by_page"].values() for a in atoms]
    assert sorted(placed) == sorted(data["atoms"]), "atom missing from by_page"
