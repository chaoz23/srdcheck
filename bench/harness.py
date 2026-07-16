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
    print("wrote", HERE / "scorecard.md", "and scorecard.json")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", required=True)
    r.add_argument("--subject", required=True,
                   help="gemini:<model> | ollama:<model> | cmd:<command>")
    sub.add_parser("score")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.set, args.subject)
        score()
    else:
        score()


if __name__ == "__main__":
    main()
