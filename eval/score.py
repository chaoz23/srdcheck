#!/usr/bin/env python3
"""Score kill-test arms per PROTOCOL.md. Usage: score.py [A B C ...]"""

import json
import os
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent
CATS = ["action-economy", "spellcasting", "conditions", "build-legality",
        "stacking", "stateful", "cannot-adjudicate"]
SUFFIX = os.environ.get("SUFFIX", "")


def score(arm):
    path = ROOT / "results" / f"arm-{arm}{SUFFIX}.jsonl"
    if not path.exists():
        return None
    recs = [json.loads(l) for l in path.open() if l.strip()]
    by_cat = defaultdict(lambda: {"n": 0, "wrong": 0, "refusal": 0,
                                  "false_conf": 0, "broken": 0})
    for r in recs:
        c = by_cat[r["category"]]
        c["n"] += 1
        got, gold = r["answer"].get("verdict"), r["gold"]
        if got in ("PARSE_FAIL", "ERROR"):
            c["broken"] += 1
        elif gold == "cannot-adjudicate" and got != "cannot-adjudicate":
            c["false_conf"] += 1
        elif gold != "cannot-adjudicate" and got == "cannot-adjudicate":
            c["refusal"] += 1
        elif got != gold:
            c["wrong"] += 1
    return recs, by_cat


def main():
    arms = sys.argv[1:] or ["A", "B", "C"]
    for arm in arms:
        res = score(arm)
        if res is None:
            print(f"\n== Arm {arm}: no results ==")
            continue
        recs, by_cat = res
        print(f"\n== Arm {arm} ({len(recs)} answered) ==")
        print(f"{'category':<18}{'n':>3}{'wrong':>7}{'refusal':>9}"
              f"{'false-conf':>12}{'broken':>8}")
        for cat in CATS:
            if cat not in by_cat:
                continue
            c = by_cat[cat]
            print(f"{cat:<18}{c['n']:>3}{c['wrong']:>7}{c['refusal']:>9}"
                  f"{c['false_conf']:>12}{c['broken']:>8}")
        adj = [r for r in recs if r["gold"] != "cannot-adjudicate"]
        wrong = sum(1 for r in adj
                    if r["answer"].get("verdict") not in
                    (r["gold"], "cannot-adjudicate", "PARSE_FAIL", "ERROR"))
        print(f"adjudicable wrong-rate: {wrong}/{len(adj)}"
              f" = {wrong/len(adj)*100:.0f}%" if adj else "")
        misses = [f"  {r['id']}: gold={r['gold']} got={r['answer'].get('verdict')}"
                  for r in recs if r["answer"].get("verdict") != r["gold"]]
        if misses:
            print("misses:")
            print("\n".join(misses))


if __name__ == "__main__":
    main()
