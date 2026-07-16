#!/usr/bin/env python3
"""Mage Hand demo: same DM model, with and without srdcheck verdicts.

3 runs per scenario per arm to expose ruling variance. Results append to
results.jsonl (skips already-done keys), so the run is resumable.
"""

import json
import pathlib
import re
import sys
import urllib.request

from srdcheck_mini import verdict

HERE = pathlib.Path(__file__).resolve().parent
RUNS = 3

DM_ROLE = """You are the Dungeon Master of a game using the 2024 D&D rules (SRD 5.2.1).
The wizard Corvo is hidden behind crates in a guard post. His Mage Hand cantrip is active (cast last turn, well within its 1-minute duration).
Player proposals must be adjudicated by the rules as written before you narrate.
Respond with ONLY a JSON object:
{"ruling": "works" | "blocked" | "gm-call", "mechanics": "one sentence: the rules basis for your ruling", "narration": "one or two sentences of in-game narration"}"""

WITH_RAILS = """
A deterministic rules engine (srdcheck) has already adjudicated this proposal against the SRD text. Its verdict is authoritative for what the rules say:
%s
If the verdict is "legal" or "illegal", your ruling must follow it. If it is "cannot-adjudicate", the rules have no answer and the ruling is genuinely yours to make as GM — make it, and make it fun."""


def gemini_key():
    text = (pathlib.Path.home() / ".openclaw/secrets/gemini.env").read_text()
    return re.search(r"GEMINI_API_KEY=(\S+)", text).group(1)


def call_model(prompt):
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


def parse(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"ruling": "PARSE_FAIL", "raw": text[:400]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"ruling": "PARSE_FAIL", "raw": text[:400]}


def main():
    out = HERE / "results.jsonl"
    done = set()
    if out.exists():
        done = {(r["id"], r["arm"], r["run"])
                for r in map(json.loads, out.open()) if r}
    scenarios = [json.loads(l) for l in (HERE / "scenarios.jsonl").open()]

    for s in scenarios:
        v = verdict(s["proposal"])
        for arm in ("no-rails", "rails"):
            for run in range(1, RUNS + 1):
                if (s["id"], arm, run) in done:
                    continue
                prompt = DM_ROLE + "\n\nScene facts: " + s["facts"]
                if arm == "rails":
                    prompt += WITH_RAILS % json.dumps(v, indent=2)
                prompt += "\n\nPlayer (Corvo): \"" + s["nl"] + "\""
                try:
                    ans = parse(call_model(prompt))
                except Exception as e:  # noqa: BLE001
                    ans = {"ruling": "ERROR", "raw": str(e)[:200]}
                rec = {"id": s["id"], "arm": arm, "run": run,
                       "srdcheck": v["verdict"], "answer": ans}
                with out.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                print(s["id"], arm, run, "->", ans.get("ruling"), flush=True)


if __name__ == "__main__":
    main()
