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
    adj, total = _counts()
    assert adj / total >= 0.64, f"in-scope coverage regressed: {adj}/{total}"


def test_out_of_scope_stays_uncovered():
    # srdcheck must never grow a query for GM/RNG/VTT work (T6)
    for ev in CORPUS:
        if SCOPE.get(ev["kind"]) == "out-of-scope":
            assert ev["route"]["type"] is None, ev["id"]
            assert classify(ev)[0] == "UNCOVERED", ev["id"]


def test_every_kind_has_a_scope():
    for ev in CORPUS:
        assert ev["kind"] in SCOPE, ev["kind"]


def test_the_concentrated_gap_is_combat_resolution():
    # documents the M1 target: HP/damage + death saves + saving throws are the
    # top closeable cluster (one coherent system)
    gap_kinds = {ev["kind"] for ev in CORPUS
                 if SCOPE.get(ev["kind"]) == "in-scope"
                 and classify(ev)[0] != "ADJUDICATED"}
    assert {"damage-hp", "death-saves", "saving-throw"} <= gap_kinds
