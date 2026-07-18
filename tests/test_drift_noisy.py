"""Noisy-transcript drift pilot correctness (Epic 5, M0).

The pilot's whole value rests on two guarantees: the gold is engine-derived (not
hand-guessed), and the load-bearing fact is actually PRESENT in every rendering
(so a subject's error is drift, not a rendering bug or an unfair omission). These
tests hold both, plus determinism and freshness."""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import drift_noisy  # noqa: E402

SET = ROOT / "bench" / "sets" / "drift_noisy.jsonl"


def test_gold_is_engine_derived():
    _, oracle = drift_noisy.generate()
    for o in oracle:
        assert o["invariant"](o["true_state"]), \
            f"{o['id']}: gold not grounded in the reducer-derived state"


def test_load_bearing_fact_present_in_every_rendering():
    # fairness: the test is retrieval-under-volume, not inference-from-ambiguity.
    # a rules-literate human reading the whole transcript must be able to get it.
    _, oracle = drift_noisy.generate()
    for o in oracle:
        for fact in o["facts"]:
            assert fact.lower() in o["question"].lower(), \
                f"{o['id']}: load-bearing fact missing: {fact!r}"


def test_filler_never_contradicts_focal_state():
    # the noise must not assert the focal creature is fine/healthy — that would
    # plant a contradiction and make a 'wrong' answer unfair.
    _, oracle = drift_noisy.generate()
    for o in oracle:
        for focal in ("Theron", "Mira"):
            assert not re.search(
                focal + r"[^.]{0,40}(they're fine|is fine|is up|looks fine)",
                o["question"]), f"{o['id']}: filler contradicts {focal}"


def test_generation_is_deterministic():
    a = "".join(json.dumps(r) + "\n" for r in drift_noisy.generate()[0])
    b = "".join(json.dumps(r) + "\n" for r in drift_noisy.generate()[0])
    assert a == b


def test_checked_in_set_matches_generator():
    fresh = "".join(json.dumps(r) + "\n" for r in drift_noisy.generate()[0])
    assert SET.read_text() == fresh, \
        "drift_noisy.jsonl is stale — rerun bench/drift_noisy.py"


def test_length_gradient_is_monotonic():
    records = drift_noisy.generate()[0]
    order = {"light": 0, "heavy": 1, "buried": 2, "epic": 3}
    by_mode = {}
    for r in records:
        by_mode.setdefault(r["category"].split("/")[0], []).append(r)
    for mode, rs in by_mode.items():
        rs.sort(key=lambda r: order[r["level"]])
        words = [r["approx_words"] for r in rs]
        assert words == sorted(words), f"{mode}: length not monotonic {words}"
        assert words[-1] > 20000, f"{mode}: epic tier too short to matter"
