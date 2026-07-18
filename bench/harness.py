#!/usr/bin/env python3
"""srdcheck bench — the rules-fidelity referee.

  python bench/harness.py run   --set core --subject ollama:qwen3:8b-q4_K_M
  python bench/harness.py run   --set core --subject gemini:gemini-pro-latest
  python bench/harness.py run   --set core --subject "cmd:./my-agent --pipe"
  python bench/harness.py score                     # regenerate scorecard.md

Subjects answer natural-language rules questions; gold verdicts derive from
SRD 5.2.1 text with citations. Scoring is per-category, wrong-rate and
refusal-rate always separated, never one blended number (truth T9).
Results are resumable; records append to bench/results/<subject>/<set>.jsonl.
"""

import argparse
import json
import pathlib
import re
import subprocess
import urllib.request
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
SETS = HERE / "sets"
RESULTS = HERE / "results"

PROMPT_VERSION = "p1"
PROMPT = """You are adjudicating a tabletop RPG rules question strictly under the System Reference Document 5.2.1 (the 2024 rules revision).
Respond with ONLY a JSON object, no other text:
{"verdict": "legal" | "illegal" | "cannot-adjudicate", "citations": ["..."], "rationale": "one or two sentences"}
Semantics: "legal" = the proposed action or claim is permitted/correct under SRD 5.2.1; "illegal" = not permitted/incorrect; "cannot-adjudicate" = the SRD rules text cannot decide this (unknown/third-party content, optional rules the SRD lacks, or GM discretion)."""


def gemini_key():
    import os
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = pathlib.Path.home() / ".openclaw/secrets/gemini.env"
    return re.search(r"GEMINI_API_KEY=(\S+)", env.read_text()).group(1)


def make_driver(spec):
    kind, _, arg = spec.partition(":")
    if kind == "gemini":
        def call(prompt):
            body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{arg}:generateContent",
                data=body, headers={"Content-Type": "application/json",
                                    "x-goog-api-key": gemini_key()})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            return d["candidates"][0]["content"]["parts"][0]["text"]
        return call
    if kind == "ollama":
        def call(prompt):
            body = json.dumps({"model": arg, "stream": False, "think": False,
                               "messages": [{"role": "user", "content": prompt}],
                               "options": {"num_predict": 400, "temperature": 0}}).encode()
            req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                         data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["message"]["content"]
        return call
    if kind == "cmd":
        def call(prompt):
            return subprocess.run(arg, shell=True, input=prompt, text=True,
                                  capture_output=True, timeout=600).stdout
        return call
    raise SystemExit(f"unknown subject kind '{kind}' (gemini|ollama|cmd)")


def parse_verdict(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"verdict": "PARSE_FAIL", "raw": text[:400]}
    try:
        obj = json.loads(m.group(0))
        obj.setdefault("verdict", "PARSE_FAIL")
        return obj
    except json.JSONDecodeError:
        return {"verdict": "PARSE_FAIL", "raw": text[:400]}


def subject_dir(subject):
    return RESULTS / re.sub(r"[^A-Za-z0-9._+-]", "_", subject)


def run(set_name, subject):
    qs = [json.loads(l) for l in (SETS / f"{set_name}.jsonl").open()]
    out = subject_dir(subject) / f"{set_name}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(l)["id"] for l in out.open() if l.strip()}
    driver = make_driver(subject)
    for q in qs:
        if q["id"] in done:
            continue
        try:
            ans = parse_verdict(driver(PROMPT + "\n\nQuestion: " + q["question"]))
        except Exception as e:  # noqa: BLE001
            ans = {"verdict": "ERROR", "raw": str(e)[:300]}
        rec = {"id": q["id"], "category": q["category"],
               "gold": q["gold"]["verdict"], "answer": ans,
               "prompt_version": PROMPT_VERSION}
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(q["id"], "gold:", q["gold"]["verdict"], "->",
              ans.get("verdict"), flush=True)


def tally(recs):
    cats = defaultdict(lambda: dict(n=0, wrong=0, refusal=0,
                                    false_conf=0, broken=0))
    for r in recs:
        c = cats[r["category"]]
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
    return cats


def score():
    """Regenerate scorecard.json + scorecard.md from everything on disk."""
    card = {}
    for sd in sorted(RESULTS.iterdir()):
        if not sd.is_dir():
            continue
        for rf in sorted(sd.glob("*.jsonl")):
            recs = [json.loads(l) for l in rf.open() if l.strip()]
            card.setdefault(rf.stem, {})[sd.name] = {
                k: dict(v) for k, v in tally(recs).items()}
    (HERE / "scorecard.json").write_text(json.dumps(card, indent=1))

    lines = ["# Rules-fidelity scorecard",
             "",
             "Per-category, wrong-rate and refusal-rate separated, no aggregate "
             "score — by design ([truth T9](../docs/product-truths.md)). "
             "Generated by `python bench/harness.py score`; never hand-edited.",
             ""]
    for set_name, subjects in sorted(card.items()):
        lines += [f"## Set: {set_name}", ""]
        lines += ["| subject | category | n | wrong | refusal | false-confidence | broken |",
                  "|---|---|--:|--:|--:|--:|--:|"]
        for subj, cats in sorted(subjects.items()):
            for cat, c in sorted(cats.items()):
                lines.append(f"| {subj} | {cat} | {c['n']} | {c['wrong']} "
                             f"| {c['refusal']} | {c['false_conf']} | {c['broken']} |")
        lines.append("")
    (HERE / "scorecard.md").write_text("\n".join(lines))
    leaderboard(card)
    print("wrote", HERE / "scorecard.md", ",", HERE / "LEADERBOARD.md",
          "and scorecard.json")


def leaderboard(card):
    """The productized referee (M3): rank subjects per set by wrong-count.

    T1 makes a wrong verdict the one categorically unforgivable failure, and
    within a set every subject answers identical questions, so wrong-count is
    exactly comparable. There is deliberately NO composite score (T9): the other
    three failure modes are shown as separate columns, never folded in — the sort
    is by one honest axis, not a blend."""
    lines = [
        "# srdcheck referee — leaderboard",
        "",
        "How faithfully does your agent or model adjudicate SRD 5.2.1 rules? "
        "Point the harness at it and it lands here — see "
        "[Get on the leaderboard](README.md#get-on-the-leaderboard).",
        "",
        "Sorted by **wrong verdicts** — the only categorically unforgivable "
        "failure ([T1](../docs/product-truths.md)). There is no composite score "
        "([T9](../docs/product-truths.md)): refusal, false-confidence, and broken "
        "are shown separately, never folded into one number. Within a set every "
        "subject answers the same questions, so wrong-count is directly "
        "comparable. Generated by `python bench/harness.py score`; never "
        "hand-edited.",
        "",
    ]
    for set_name, subjects in sorted(card.items()):
        rows = []
        for subj, cats in subjects.items():
            agg = {k: sum(c[k] for c in cats.values())
                   for k in ("n", "wrong", "refusal", "false_conf", "broken")}
            rows.append((subj, agg))
        # sort key: wrong first (T1), then the remaining modes; all shown anyway
        rows.sort(key=lambda r: (r[1]["wrong"], r[1]["false_conf"],
                                 r[1]["refusal"], r[1]["broken"], r[0]))
        n = rows[0][1]["n"] if rows else 0
        lines += [f"## Set: {set_name} (n={n})", ""]
        lines += ["| rank | subject | wrong | refusal | false-confidence | broken |",
                  "|--:|---|--:|--:|--:|--:|"]
        for i, (subj, a) in enumerate(rows):
            ahead = sum(1 for _, b in rows
                        if (b["wrong"], b["false_conf"], b["refusal"], b["broken"])
                        < (a["wrong"], a["false_conf"], a["refusal"], a["broken"]))
            lines.append(f"| {ahead + 1} | {subj} | {a['wrong']} | {a['refusal']} "
                         f"| {a['false_conf']} | {a['broken']} |")
        lines.append("")
    (HERE / "LEADERBOARD.md").write_text("\n".join(lines))


def validate_results(set_name, recs):
    """Check a subject's result records against the set (submission integrity).

    A submission is only trustworthy if it answered THIS set's questions and did
    not doctor the gold. Returns a list of error strings (empty = valid)."""
    gold = {q["id"]: q for q in (json.loads(l) for l in
                                 (SETS / f"{set_name}.jsonl").open())}
    errs = []
    for i, r in enumerate(recs):
        rid = r.get("id", f"<record {i}>")
        if rid not in gold:
            errs.append(f"{rid}: not an id in set '{set_name}'")
            continue
        q = gold[rid]
        if r.get("gold") != q["gold"]["verdict"]:
            errs.append(f"{rid}: recorded gold '{r.get('gold')}' != set gold "
                        f"'{q['gold']['verdict']}' (doctored or stale)")
        if r.get("category") != q["category"]:
            errs.append(f"{rid}: category '{r.get('category')}' != set "
                        f"'{q['category']}'")
        if not isinstance(r.get("answer"), dict) or "verdict" not in r["answer"]:
            errs.append(f"{rid}: missing answer.verdict")
    seen = [r.get("id") for r in recs]
    if len(seen) != len(set(seen)):
        errs.append("duplicate ids in submission")
    return errs


def validate(set_name, subject):
    rf = subject_dir(subject) / f"{set_name}.jsonl"
    if not rf.exists():
        raise SystemExit(f"no results at {rf}")
    recs = [json.loads(l) for l in rf.open() if l.strip()]
    errs = validate_results(set_name, recs)
    if errs:
        print(f"INVALID ({len(errs)}):")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    total = len({json.loads(l)["id"] for l in (SETS / f"{set_name}.jsonl").open()})
    print(f"valid: {len(recs)}/{total} of set '{set_name}' answered by {subject}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", required=True)
    r.add_argument("--subject", required=True,
                   help="gemini:<model> | ollama:<model> | cmd:<command>")
    sub.add_parser("score")
    v = sub.add_parser("validate", help="check a submission against the set")
    v.add_argument("--set", required=True)
    v.add_argument("--subject", required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.set, args.subject)
        score()
    elif args.cmd == "validate":
        validate(args.set, args.subject)
    else:
        score()


if __name__ == "__main__":
    main()
