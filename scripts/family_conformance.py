#!/usr/bin/env python3
"""family-conformance — execute a check-family tool's documented exit contract and
assert the real CLI behaves the way its SKILL.md says it does.

Closes the gap the 2026-08-16 family audit found. Every member's SKILL.md passed the
clause-7 acceptance test ("a fresh-context agent, given only this file, can produce a
well-formed invocation") on 2026-08-09 -- and all four still misstated their own
exit-code contract. That test checked *invocability*. Nothing checked *truth*.

This checks truth: it runs the tool, observes exit codes and which stream carried the
payload, and diffs that against what SKILL.md claims.

Exit codes (this tool obeys the family contract it enforces, per FAMILY.md clause 1):
  0  conformant
  1  findings
  2  cannot adjudicate -- no SKILL.md, no entry point, or the CLI would not run

All probes are read-only: --help, --schema, a nonexistent flag, and a verb pointed at a
path that does not exist. Nothing is written, installed, or mutated.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:                                    # tomllib is 3.11+; this repo supports 3.10
    import tomllib
except ModuleNotFoundError:             # pragma: no cover
    tomllib = None

SCHEMA = {
    "schema_version": "1.0",
    "tool": "family-conformance",
    "input": {"repo": "path to a check-family repo checkout"},
    "output": {
        "tool": "str", "entry": "list[str]", "conformant": "bool",
        "documented_codes": "list[int]", "observed_codes": "list[int]",
        "findings": [{"rule": "str", "severity": "high|medium|low",
                      "message": "str", "evidence": "str"}],
    },
    "exit_codes": {"0": "conformant", "1": "findings", "2": "cannot adjudicate"},
}

# Structured-failure probes per known member. An argparse usage error is not enough to
# test stream claims -- those are about the tool's own failure envelopes -- so each
# member gets one read-only invocation that provokes a real envelope. A repo may
# override this with family-probes.json at its root.
BUILTIN_PROBES = {
    "srdcheck":       ["jurisdiction", "ZZZ-no-such-name-conformance-probe"],
    "charactercheck": ["derive", "/nonexistent/conformance-probe.json"],
    "dmcheck":        ["run", "/nonexistent/conformance-probe.json"],
    "tablekit":       ["report"],
}

HONEST_MARKERS = (
    "honest", "cannot", "can't", "do not retry", "don't retry", "never retry",
    "route it to a human", "to a human", "up to the dm", "discretion", "ambiguous",
    "not present in any loaded ruleset", "unhandled", "first-class",
)
USAGE_MARKERS = ("usage", "internal error", "fix the call", "bad flag", "invalid flag")


def oneline(s: str, n: int = 150) -> str:
    """Collapse whitespace so a dumped help screen stays one readable evidence line."""
    s = " ".join(str(s).split())
    return s[:n] + ("…" if len(s) > n else "")


def die(msg: str) -> None:
    print(json.dumps({"action": "cannot_adjudicate", "reason": msg}), flush=True)
    sys.exit(2)


# ---------------------------------------------------------------- discovery


def _project_scripts(pyproject: Path) -> dict[str, str]:
    """Read [project.scripts]. Falls back to a regex on Python 3.10, which has no
    tomllib -- the only table needed is a flat name = "module:attr" mapping."""
    text = pyproject.read_text()
    if tomllib is not None:
        return tomllib.loads(text).get("project", {}).get("scripts", {})
    out, in_table = {}, False
    for ln in text.splitlines():
        stripped = ln.strip()
        if stripped.startswith("["):
            in_table = stripped == "[project.scripts]"
            continue
        if in_table:
            m = re.match(r'([A-Za-z0-9_.-]+)\s*=\s*["\'](.+?)["\']', stripped)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def discover_entry(repo: Path) -> tuple[str, list[str]]:
    """Return (tool_name, argv_prefix). Prefers the repo's own venv."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        die(f"{repo}: no pyproject.toml")
    scripts = _project_scripts(pyproject)
    # The primary console script is the one whose name has no -mcp/-server suffix.
    primary = next((n for n in scripts if not n.endswith(("-mcp", "-server"))), None)
    if not primary:
        die(f"{repo}: no console script in [project.scripts]")

    target = scripts[primary]                      # e.g. "srdcheck.cli:script"
    module = target.split(":", 1)[0]               # e.g. "srdcheck.cli"

    venv_bin = repo / ".venv" / "bin"
    if (venv_bin / primary).is_file():
        return primary, [str(venv_bin / primary)]
    # -W ignore matters: `python -m pkg.cli` can emit a runpy RuntimeWarning on
    # stderr, and stderr content is load-bearing for the stream check below. An
    # interpreter warning would make a stdout-only failure look like "both".
    if (venv_bin / "python").is_file():
        return primary, [str(venv_bin / "python"), "-W", "ignore", "-m", module]
    return primary, [sys.executable, "-W", "ignore", "-m", module]


def run(repo: Path, argv: list[str], args: list[str], stdin: str = "") -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONWARNINGS="ignore",
               PYTHONPATH=str(repo))
    try:
        p = subprocess.run(argv + args, cwd=repo, env=env, input=stdin,
                           capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"args": args, "code": None, "stdout": "", "stderr": "TIMEOUT"}
    except OSError as e:
        return {"args": args, "code": None, "stdout": "", "stderr": f"OSERROR {e}"}
    return {"args": args, "code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


# ---------------------------------------------------------------- SKILL.md parsing


def parse_skill(skill: Path) -> dict:
    """Extract the documented exit contract.

    The four members each write it a different way -- backticked runs
    (```0` = clean · `1` = findings``), bare-number prose
    (``0 passes · 1 conflicts``), a markdown table, and "exit N" sentences --
    so all four shapes must parse. Prose also wraps across source lines, so the unit
    of matching is the PARAGRAPH, not the line: dmcheck's stream claim splits as
    "Failures print JSON on" / "stderr, never a traceback." and a line-based matcher
    silently sees neither half.
    """
    raw = skill.read_text().splitlines()

    # Drop fenced blocks: `# exit 2: ...` inside an example is an illustration of a
    # call, not a statement of contract.
    body, fenced, heading = [], False, ""
    for ln in raw:
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if ln.lstrip().startswith("#"):
            heading = ln.lower()
        body.append((heading, ln))

    paragraphs, cur, cur_head = [], [], ""
    for head, ln in body:
        if ln.strip():
            if not cur:
                cur_head = head
            cur.append(ln.strip())
        elif cur:
            paragraphs.append((cur_head, " ".join(cur)))
            cur = []
    if cur:
        paragraphs.append((cur_head, " ".join(cur)))

    documented: dict[int, list[str]] = {}
    # "tight" contexts are the code's OWN clause ("`2` = unusable input", a table row).
    # "loose" ones are whole paragraphs picked up by an "exit N" mention, which drag in
    # sentences describing neighbouring codes. Classifying a code by loose context makes
    # every code look like the honest lane, so markers are read from tight context only.
    tight: dict[int, list[str]] = {}

    def record(code: int, ctx: str, is_tight: bool = False) -> None:
        if not 0 <= code <= 3:
            return
        ctx = " ".join(ctx.split())[:220]
        documented.setdefault(code, []).append(ctx)
        if is_tight:
            tight.setdefault(code, []).append(ctx)

    # Markdown contract tables, read from raw lines (paragraph-joining destroys rows).
    for _, ln in body:
        row = re.match(r"\s*\|\s*`?(\d)`?\s*\|(.+)", ln)
        if row:
            record(int(row.group(1)), ln, is_tight=True)

    for head, para in paragraphs:
        for m in re.finditer(r"\bexit(?:\s+code)?\s*[:\s]\s*(\d)\b", para, re.I):
            record(int(m.group(1)), para)
        if "exit" not in head and "exit" not in para.lower():
            continue
        # "`0` = clean" / "0 passes the named scope" / "· 2 cannot-adjudicate"
        for m in re.finditer(r"(?:^|[·(\s])`?([0-3])`?\s*(?:=|\s)\s*([A-Za-z][^·|]{2,90})", para):
            record(int(m.group(1)), f"{m.group(1)} {m.group(2)}", is_tight=True)

    honest, usage = set(), set()
    for code in documented:
        ctxs = tight.get(code) or documented.get(code, [])
        blob = " ".join(ctxs).lower()
        if any(k in blob for k in HONEST_MARKERS):
            honest.add(code)
        if any(k in blob for k in USAGE_MARKERS):
            usage.add(code)

    stream_claim = None
    for _, para in paragraphs:
        low = para.lower()
        if ("stderr" in low or "stdout" in low) and any(
                w in low for w in ("fail", "error", "envelope", "invalid", "print")):
            stream_claim = ("stderr" if "stderr" in low else "stdout", para)
            break

    return {"documented": documented, "tight": tight, "honest": honest,
            "usage": usage, "stream_claim": stream_claim}


# ---------------------------------------------------------------- the checks


def audit(repo: Path) -> dict:
    repo = repo.resolve()
    skill = repo / "SKILL.md"
    if not skill.is_file():
        die(f"{repo}: no SKILL.md -- nothing declares a contract to check")

    tool, argv = discover_entry(repo)
    parsed = parse_skill(skill)
    findings: list[dict] = []

    def add(rule, severity, message, evidence):
        findings.append({"rule": rule, "severity": severity,
                         "message": message, "evidence": evidence})

    help_p = run(repo, argv, ["--help"])
    if help_p["code"] is None:
        die(f"{repo}: CLI would not run ({help_p['stderr'][:120]})")

    schema_p = run(repo, argv, ["--schema"])
    badflag_p = run(repo, argv, ["--zzz-not-a-real-flag"])
    probe_args = BUILTIN_PROBES.get(tool)
    override = repo / "family-probes.json"
    if override.is_file():
        probe_args = json.loads(override.read_text()).get("failure_probe", probe_args)
    envelope_p = run(repo, argv, probe_args) if probe_args else None

    # --- clause 7: the flags are codified by name -------------------------------
    pipe_p = run(repo, argv, ["--pipe"], stdin="")
    if "unrecognized arguments: --pipe" in pipe_p["stderr"] or \
       "unknown option" in pipe_p["stderr"] or "unknown command" in pipe_p["stderr"]:
        add("MISSING_PIPE", "high",
            "FAMILY.md clause 7 codifies `--pipe` by name; the CLI rejects it.",
            f"`{tool} --pipe` -> exit {pipe_p['code']}: {oneline(pipe_p['stderr'])}")

    if schema_p["code"] != 0:
        add("SCHEMA_NOT_FLAG", "high",
            "FAMILY.md clause 7 codifies `--schema` as a flag; the CLI rejects it "
            "(a `schema` subcommand does not discharge the clause -- a fresh agent "
            "following FAMILY.md is refused).",
            f"`{tool} --schema` -> exit {schema_p['code']}: {oneline(schema_p['stderr'])}")
    elif schema_p["stdout"].strip():
        try:
            json.loads(schema_p["stdout"])
        except json.JSONDecodeError:
            add("SCHEMA_NOT_JSON", "medium",
                "`--schema` exits 0 but stdout is not valid JSON.",
                oneline(schema_p["stdout"]))

    # --- clause 1: every code the tool actually returns must be documented -------
    # --help and --schema are meta surfaces, not verdict paths -- their exit 0 is
    # universal and no SKILL.md needs to document it. Only verdict-bearing probes
    # count toward the "every code must be documented" rule.
    observed: dict[int, str] = {}
    for p in [badflag_p, envelope_p]:
        if p and p["code"] is not None:
            observed.setdefault(p["code"], f"`{tool} {' '.join(p['args'])}`")
    for code, how in sorted(observed.items()):
        if code not in parsed["documented"]:
            add("UNDOCUMENTED_EXIT_CODE", "high",
                f"CLI returns exit {code}, which SKILL.md never documents. An agent "
                f"following the file cannot classify this outcome.",
                f"{how} -> exit {code}; SKILL.md documents "
                f"{sorted(parsed['documented']) or 'nothing'}")

    # --- clause 1: the honest lane must not be overloaded with usage errors ------
    bad_code = badflag_p["code"]
    for hc in sorted(parsed["honest"]):
        if bad_code == hc and hc not in parsed["usage"]:
            # Quote the clause that actually carries the honest-lane language, not
            # whichever context happened to be recorded first.
            ctxs = parsed["tight"].get(hc) or parsed["documented"].get(hc, [""])
            ctx = oneline(next((c for c in ctxs
                                if any(k in c.lower() for k in HONEST_MARKERS)), ctxs[0]), 170)
            # medium, not high: this fires on most of the family, and a rule that
            # flags the majority at high severity trains readers to ignore it. The
            # honest lane still works -- what is wrong is that SKILL.md does not let
            # an agent tell a refusal apart from its own bad call.
            add("HONEST_LANE_OVERLOAD", "medium",
                f"SKILL.md reserves exit {hc} for the cannot-adjudicate lane and tells "
                f"agents to route it to a human without retrying -- but a plain usage "
                f"error also returns {hc}. An agent obeying the file escalates its own "
                f"malformed calls to a human as if they were rulings.",
                f"`{tool} --zzz-not-a-real-flag` -> exit {bad_code}. SKILL.md: \"{ctx}\"")

    # --- clause 1: stream claims must match observed behaviour -------------------
    if parsed["stream_claim"] and envelope_p and envelope_p["code"] not in (0, None):
        claimed, line = parsed["stream_claim"]
        got_out, got_err = bool(envelope_p["stdout"].strip()), bool(envelope_p["stderr"].strip())
        actual = "stdout" if got_out and not got_err else \
                 "stderr" if got_err and not got_out else \
                 "both" if got_out and got_err else "neither"
        if actual not in (claimed, "both"):
            add("STREAM_MISMATCH", "high",
                f"SKILL.md says failure output goes to {claimed}; it actually goes to "
                f"{actual}. An agent reading {claimed} for the failure payload sees nothing.",
                f"`{tool} {' '.join(envelope_p['args'])}` -> exit {envelope_p['code']}, "
                f"stdout {len(envelope_p['stdout'])}B / stderr {len(envelope_p['stderr'])}B. "
                f"SKILL.md: \"{oneline(line, 130)}\"")

    return {
        "tool": tool,
        "repo": str(repo),
        "entry": argv,
        "documented_codes": sorted(parsed["documented"]),
        "observed_codes": sorted(observed),
        "honest_lane_codes": sorted(parsed["honest"]),
        "conformant": not findings,
        "findings": findings,
    }


# ---------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="family-conformance",
        description="Assert a check-family tool's CLI matches its SKILL.md contract.")
    ap.add_argument("repos", nargs="*", type=Path, help="repo checkout path(s)")
    ap.add_argument("--pipe", action="store_true",
                    help="read repo paths from stdin, one per line; one JSON result per line")
    ap.add_argument("--schema", action="store_true", help="print the I/O contract and exit 0")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.schema:
        print(json.dumps(SCHEMA, indent=2))
        return 0

    targets = [Path(l.strip()) for l in sys.stdin if l.strip()] if args.pipe else args.repos
    if not targets:
        ap.error("no repos given (pass paths, or --pipe with paths on stdin)")

    results, worst = [], 0
    for repo in targets:
        r = audit(repo)
        results.append(r)
        worst = max(worst, 1 if r["findings"] else 0)
        if args.pipe:
            print(json.dumps(r), flush=True)

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    elif not args.pipe:
        for r in results:
            mark = "PASS" if r["conformant"] else "FAIL"
            print(f"\n{mark}  {r['tool']}  ({r['repo']})")
            print(f"      documented {r['documented_codes']} · observed {r['observed_codes']}"
                  f" · honest-lane {r['honest_lane_codes']}")
            for f in r["findings"]:
                print(f"  [{f['severity']}] {f['rule']}")
                print(f"      {f['message']}")
                print(f"      evidence: {f['evidence']}")
        total = sum(len(r["findings"]) for r in results)
        print(f"\n{total} finding(s) across {len(results)} repo(s)")
    return worst


if __name__ == "__main__":
    sys.exit(main())
