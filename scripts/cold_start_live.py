#!/usr/bin/env python3
"""Live cold-start probe (T10): hand a model ONLY tool.json and ask it to
produce its first verdict command. Executed under a strict allowlist
(must invoke srdcheck; nothing else runs). Records evidence to
bench/results/cold-start.json. Run on demand, not in CI (model in loop).
"""

import json
import pathlib
import re
import shlex
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "bench" / "results" / "cold-start.json"
ALLOWED = re.compile(r"^(python3?\s+-m\s+srdcheck|srdcheck)\b")


def gemini(prompt):
    key_file = pathlib.Path.home() / ".openclaw/secrets/gemini.env"
    import os
    key = os.environ.get("GEMINI_API_KEY") or re.search(
        r"GEMINI_API_KEY=(\S+)", key_file.read_text()).group(1)
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro-latest:generateContent",
        data=body, headers={"Content-Type": "application/json",
                            "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]


def main():
    tool_json = (ROOT / "tool.json").read_text()
    task = ("You are an agent on a machine with a tool described by the "
            "following tool.json (working directory is the tool's repo "
            "root). Your goal: determine whether 'Grappled' is known "
            "content. Reply with ONLY the single shell command to run — "
            "no prose, no backticks.\n\n" + tool_json)
    t0 = time.time()
    attempts = []
    verdict = None
    for i in range(1, 4):
        cmd = gemini(task if i == 1 else
                     task + f"\n\nYour previous command failed with: "
                            f"{attempts[-1]['error']}. Reply with only a "
                            "corrected command.").strip().strip("`")
        entry = {"attempt": i, "command": cmd}
        if not ALLOWED.match(cmd):
            entry["error"] = "refused: not an srdcheck invocation"
            attempts.append(entry)
            continue
        argv = shlex.split(cmd)
        if argv[0].startswith("python"):
            argv[0] = sys.executable
        r = subprocess.run(argv, capture_output=True, text=True,
                           cwd=ROOT, timeout=60)
        try:
            verdict = json.loads(r.stdout)
            entry["exit_code"] = r.returncode
            attempts.append(entry)
            break
        except json.JSONDecodeError:
            entry["error"] = (r.stdout or r.stderr)[:200]
            attempts.append(entry)
    result = {
        "date": time.strftime("%Y-%m-%d"),
        "model": "gemini-pro-latest",
        "task": "first verdict from tool.json alone",
        "attempts_to_first_verdict": len(attempts) if verdict else None,
        "elapsed_s": round(time.time() - t0, 1),
        "success": bool(verdict and verdict.get("exit_code") == 0
                        and "Grappled" in verdict.get("why", "")),
        "verdict_exit_code": verdict.get("exit_code") if verdict else None,
        "attempts": attempts,
    }
    EVIDENCE.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
