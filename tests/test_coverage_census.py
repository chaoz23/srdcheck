"""Coverage census as a ratcheting bench lane (Measured Engine M0).

Coverage of in-scope combat events is a floor that each engine slice raises.
Out-of-scope events (GM discretion / RNG / VTT geometry) must STAY uncovered —
covering them would be a T6 violation, not progress."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from coverage import CORPUS, SCOPE, classify  # noqa: E402


def _counts():
    adj = total = 0
    for ev in CORPUS:
        if SCOPE.get(ev["kind"]) != "in-scope":
            continue
        total += 1
        if classify(ev)[0] == "ADJUDICATED":
            adj += 1
    return adj, total


def test_in_scope_coverage_floor():
    # ratchet: raise this floor whenever an engine slice closes a gap. Never lower.
    # 0.64 (M0 census) -> 0.89 (M1 combat resolution) -> 1.0 (condition
    # completeness pass: every SRD condition now adjudicates on the built
    # surfaces; see test_condition_completeness). At 1.0, a new in-scope event
    # for an unbuilt effect is meant to fail here — model it or classify it.
    adj, total = _counts()
    assert adj / total >= 1.0, f"in-scope coverage regressed: {adj}/{total}"


def test_out_of_scope_stays_uncovered():
    # srdcheck must never grow a query for GM/RNG/VTT work (T6)
    for ev in CORPUS:
        if SCOPE.get(ev["kind"]) == "out-of-scope":
            assert ev["route"]["type"] is None, ev["id"]
            assert classify(ev)[0] == "UNCOVERED", ev["id"]


def test_every_kind_has_a_scope():
    for ev in CORPUS:
        assert ev["kind"] in SCOPE, ev["kind"]


def test_combat_resolution_gap_is_closed():
    # M1 closed the concentrated combat-resolution cluster that the M0 census
    # identified. These must now adjudicate; regressing any is a ratchet break.
    adjudicated = {ev["kind"] for ev in CORPUS
                   if classify(ev)[0] == "ADJUDICATED"}
    assert {"damage-hp", "death-saves", "saving-throw"} <= adjudicated
