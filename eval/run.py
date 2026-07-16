#!/usr/bin/env python3
"""Phase 0 kill-test runner. Usage: run.py A|B|C [start_idx]

Arm A: frontier model (claude CLI, opus), question only.
Arm B: same model, question + SRD excerpt pages parsed from gold citations.
Arm C: local qwen3:8b via ollama, question only (informational floor).

Results append to eval/results/arm-<X>.jsonl (skips ids already present).
"""

import json
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"
PAGES = ROOT / "sources" / "text"

SYSTEM = """You are adjudicating a tabletop RPG rules question strictly under the System Reference Document 5.2.1 (the 2024 rules revision).
Respond with ONLY a JSON object, no other text:
{"verdict": "legal" | "illegal" | "cannot-adjudicate", "citations": ["..."], "rationale": "one or two sentences"}
Semantics: "legal" = the proposed action or claim is permitted/correct under SRD 5.2.1; "illegal" = not permitted/incorrect; "cannot-adjudicate" = the SRD rules text cannot decide this (unknown/third-party content, optional rules the SRD lacks, or GM discretion)."""


def excerpt_for(q):
    pages = set()
    for c in q["gold"]["citations"]:
        for m in re.findall(r"p\.(\d+)(?:-(\d+))?", c):
            lo = int(m[0])
            hi = int(m[1]) if m[1] else lo
            pages.update(range(lo, hi + 1))
    texts = []
    for p in sorted(pages):
        f = PAGES / f"page-{p:03d}.txt"
        if f.exists():
            texts.append(f"--- SRD 5.2.1 page {p} ---\n{f.read_text()}")
    return "\n".join(texts)


def gemini_key():
    text = (pathlib.Path.home() / ".openclaw/secrets/gemini.env").read_text()
    return re.search(r"GEMINI_API_KEY=(\S+)", text).group(1)


def call_frontier(prompt):
    # gemini-pro-latest (resolves to Gemini 3.1 Pro as of 2026-07).
    # Chosen over the claude CLI (no auth in nested sessions) and it also
    # avoids same-family bias with the gold-set curator model.
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro-latest:generateContent",
        data=body,
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": gemini_key()},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        d = json.load(resp)
    return d["candidates"][0]["content"]["parts"][0]["text"].strip()


def call_ollama(prompt):
    body = json.dumps({
        "model": "qwen3:8b-q4_K_M",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_predict": 400, "temperature": 0},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["message"]["content"].strip()


def parse_verdict(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"verdict": "PARSE_FAIL", "raw": text[:500]}
    try:
        obj = json.loads(m.group(0))
        obj.setdefault("verdict", "PARSE_FAIL")
        return obj
    except json.JSONDecodeError:
        return {"verdict": "PARSE_FAIL", "raw": text[:500]}


def main():
    arm = sys.argv[1]
    qfile = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else QUESTIONS
    suffix = "" if qfile == QUESTIONS else "-" + qfile.stem.replace("questions-", "")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"arm-{arm}{suffix}.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(l)["id"] for l in out.open() if l.strip()}

    qs = [json.loads(l) for l in qfile.open()]
    for q in qs:
        if q["id"] in done:
            continue
        prompt = SYSTEM + "\n\nQuestion: " + q["question"]
        if arm == "B":
            ex = excerpt_for(q)
            if ex:
                prompt += "\n\nRelevant SRD 5.2.1 excerpts:\n" + ex
        try:
            raw = call_ollama(prompt) if arm == "C" else call_frontier(prompt)
            ans = parse_verdict(raw)
        except Exception as e:  # noqa: BLE001 — record and continue
            ans = {"verdict": "ERROR", "raw": str(e)[:300]}
        rec = {"id": q["id"], "category": q["category"],
               "gold": q["gold"]["verdict"], "answer": ans}
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(q["id"], "gold:", q["gold"]["verdict"], "->", ans.get("verdict"), flush=True)


if __name__ == "__main__":
    main()
