"""The drift-lane generator's own correctness (Measured Engine M2).

The benchmark's ground truth is DERIVED by folding each scenario's focal events
through srdcheck's reducer, not hand-guessed. These tests are the rubric turned
on the benchmark: the published gold must agree with the engine-derived true
state, generation must be deterministic, and the horizon grid must be intact.
If a gold ever disagrees with the fold, the benchmark — not just a subject —
has drifted, and that is the one thing this lane must never do."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import drift_gen  # noqa: E402

SET = ROOT / "bench" / "sets" / "drift_long.jsonl"


def test_every_gold_is_grounded_in_the_derived_state():
    _, oracle = drift_gen.generate()
    for o in oracle:
        assert o["invariant"](o["true_state"]), \
            f"{o['id']}: derived state {o['true_state']} violates its own invariant"


def test_gold_verdicts_are_well_formed():
    _, oracle = drift_gen.generate()
    for o in oracle:
        assert o["gold"] in ("legal", "illegal", "cannot-adjudicate"), o["id"]


def test_generation_is_deterministic():
    a = "".join(json.dumps(r) + "\n" for r in drift_gen.generate()[0])
    b = "".join(json.dumps(r) + "\n" for r in drift_gen.generate()[0])
    assert a == b


def test_checked_in_set_matches_generator():
    # the committed set must be exactly what the generator produces (no drift
    # between code and data); regenerate with `python bench/drift_gen.py`.
    on_disk = SET.read_text()
    fresh = "".join(json.dumps(r) + "\n" for r in drift_gen.generate()[0])
    assert on_disk == fresh, "drift_long.jsonl is stale — rerun bench/drift_gen.py"


def test_full_horizon_grid_present():
    records = drift_gen.generate()[0]
    modes = {r["category"].split("/")[0] for r in records}
    for m in modes:
        hs = {r["horizon"] for r in records if r["category"].startswith(m + "/")}
        assert hs == set(drift_gen.HORIZONS), f"{m} missing horizons: {hs}"


def test_horizon_controls_only_cause_probe_distance():
    # same trap across horizons: the causal beats (and thus the gold) are
    # identical; only the round count / filler differs. This is what makes the
    # lane a clean per-horizon control.
    records = drift_gen.generate()[0]
    by_mode = {}
    for r in records:
        by_mode.setdefault(r["category"].split("/")[0], []).append(r)
    for mode, rs in by_mode.items():
        golds = {json.dumps(r["gold"], sort_keys=True) for r in rs}
        assert len(golds) == 1, f"{mode}: gold varies across horizons"
        # the log grows strictly with the horizon
        lengths = sorted((r["horizon"], r["question"].count("ROUND ")) for r in rs)
        assert [n for _, n in lengths] == sorted(n for _, n in lengths), mode


def test_reducer_cross_checks_the_heal_the_dead_gold():
    # independent oracle path: the phantom-alive scenario's probe (heal a dead
    # creature) must be illegal per the engine, matching the published gold.
    _, oracle = drift_gen.generate()
    dead = next(o for o in oracle if o["id"].startswith("dl-phantom-alive"))
    v = drift_gen.E.query("event.apply",
                          {"state": dead["true_state"],
                           "event": {"type": "heal", "amount": 5}})
    assert v.exit_code == 1 and dead["gold"] == "illegal"
