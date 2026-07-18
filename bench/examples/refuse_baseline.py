#!/usr/bin/env python3
"""Reference `cmd:` subject for the srdcheck referee — the maximally-cautious
floor. It reads the harness prompt + question on stdin and prints one verdict
JSON object on stdout. This one always refuses; it exists to document the
contract and to give the leaderboard a meaningful floor (a subject that is never
*wrong* but is useless — it refuses everything, T8 taken to absurdity).

Your real agent replaces the body: read the question, decide, print the same
JSON shape.

    python bench/harness.py run --set core \\
        --subject "cmd:python bench/examples/refuse_baseline.py"
"""

import json
import sys


def answer(prompt):  # noqa: ARG001 — the baseline ignores the question by design
    return {"verdict": "cannot-adjudicate",
            "citations": [],
            "rationale": "This baseline refuses every question."}


if __name__ == "__main__":
    print(json.dumps(answer(sys.stdin.read())))
