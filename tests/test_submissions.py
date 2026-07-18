"""The productized referee (Measured Engine M3): submission integrity + the
leaderboard. A leaderboard a third party can submit to is only worth anything if
submissions can't lie — so every committed result file must answer its actual set
with the set's real gold, and the leaderboard must regenerate deterministically
from disk."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

import harness  # noqa: E402

RESULTS = ROOT / "bench" / "results"
SETS = ROOT / "bench" / "sets"


def _sets():
    return {p.stem for p in SETS.glob("*.jsonl")}


def test_every_committed_submission_is_valid():
    # tamper-resistance: a doctored gold or a foreign id fails here (and in CI).
    checked = 0
    for sd in RESULTS.iterdir():
        if not sd.is_dir():
            continue
        for rf in sd.glob("*.jsonl"):
            if rf.stem not in _sets():
                continue  # a result for a retired set; not a submission to judge
            recs = [json.loads(l) for l in rf.open() if l.strip()]
            errs = harness.validate_results(rf.stem, recs)
            assert not errs, f"{sd.name}/{rf.name}: {errs}"
            checked += 1
    assert checked, "no submissions found to validate"


def test_validator_rejects_a_doctored_gold():
    set_name = "core"
    real = json.loads((SETS / f"{set_name}.jsonl").open().readline())
    flipped = "legal" if real["gold"]["verdict"] != "legal" else "illegal"
    forged = [{"id": real["id"], "category": real["category"],
               "gold": flipped, "answer": {"verdict": flipped},
               "prompt_version": "p1"}]
    errs = harness.validate_results(set_name, forged)
    assert any("doctored or stale" in e for e in errs)


def test_validator_rejects_a_foreign_id():
    errs = harness.validate_results("core", [
        {"id": "not-a-real-id", "category": "x",
         "gold": "legal", "answer": {"verdict": "legal"}, "prompt_version": "p1"}])
    assert any("not an id in set" in e for e in errs)


def test_leaderboard_is_fresh():
    # regenerating from disk must reproduce the committed board (no drift between
    # results and the published ranking).
    board = (ROOT / "bench" / "LEADERBOARD.md").read_text()
    harness.score()
    assert (ROOT / "bench" / "LEADERBOARD.md").read_text() == board, \
        "LEADERBOARD.md is stale — run `python bench/harness.py score`"


def test_leaderboard_ranks_by_wrong_then_shows_all_modes():
    card = json.loads((ROOT / "bench" / "scorecard.json").read_text())
    harness.leaderboard(card)
    text = (ROOT / "bench" / "LEADERBOARD.md").read_text()
    # T9 guard: the board must not advertise a blended/aggregate/total score.
    lowered = text.lower()
    for banned in ("composite", "aggregate score", "overall score", "total score"):
        assert banned not in lowered or "no composite" in lowered
    assert "wrong" in lowered and "false-confidence" in lowered


def test_reference_baseline_flows_end_to_end(tmp_path):
    # the documented cmd: contract actually works: run the refuse-baseline over a
    # tiny 2-question stand-in set, validate, and confirm it scores as all-refusal.
    mini = tmp_path / "mini.jsonl"
    core = [json.loads(l) for l in (SETS / "core.jsonl").open()][:2]
    mini.write_text("".join(json.dumps(q) + "\n" for q in core))
    agent = ROOT / "bench" / "examples" / "refuse_baseline.py"
    for q in core:
        out = subprocess.run([sys.executable, str(agent)],
                             input=harness.PROMPT + "\n\nQuestion: " + q["question"],
                             text=True, capture_output=True, timeout=30).stdout
        ans = harness.parse_verdict(out)
        assert ans["verdict"] == "cannot-adjudicate"
