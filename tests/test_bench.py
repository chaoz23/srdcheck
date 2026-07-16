"""Bench integrity: sets are well-formed, scoring is correct, scorecard fresh."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from harness import tally  # noqa: E402

SETS = ROOT / "bench" / "sets"


def _load(name):
    return [json.loads(l) for l in (SETS / f"{name}.jsonl").open()]


def test_sets_well_formed():
    for name in ("core", "stateful"):
        qs = _load(name)
        ids = [q["id"] for q in qs]
        assert len(ids) == len(set(ids))
        for q in qs:
            gold = q["gold"]
            assert gold["verdict"] in ("legal", "illegal", "cannot-adjudicate")
            if gold["verdict"] == "cannot-adjudicate":
                continue
            assert gold["citations"], q["id"]
            assert all("SRD 5.2.1" in c for c in gold["citations"]), q["id"]


def test_core_set_composition():
    qs = _load("core")
    assert len(qs) == 30
    ca = [q for q in qs if q["gold"]["verdict"] == "cannot-adjudicate"]
    assert len(ca) >= 3
    traps = [q for q in qs if "EDITION TRAP" in q["provenance"]]
    assert len(traps) >= 3


def test_tally_failure_modes():
    recs = [
        {"category": "x", "gold": "legal", "answer": {"verdict": "legal"}},
        {"category": "x", "gold": "legal", "answer": {"verdict": "illegal"}},
        {"category": "x", "gold": "legal",
         "answer": {"verdict": "cannot-adjudicate"}},
        {"category": "x", "gold": "cannot-adjudicate",
         "answer": {"verdict": "legal"}},
        {"category": "x", "gold": "legal", "answer": {"verdict": "PARSE_FAIL"}},
    ]
    c = tally(recs)["x"]
    assert (c["n"], c["wrong"], c["refusal"], c["false_conf"], c["broken"]) \
        == (5, 1, 1, 1, 1)


def test_scorecard_is_fresh():
    """The committed scorecard must match a regeneration (never hand-edited)."""
    before = (ROOT / "bench" / "scorecard.md").read_text()
    subprocess.run([sys.executable, str(ROOT / "bench" / "harness.py"),
                    "score"], check=True, capture_output=True)
    assert (ROOT / "bench" / "scorecard.md").read_text() == before
