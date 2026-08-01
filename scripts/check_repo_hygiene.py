#!/usr/bin/env python3
"""Repo hygiene gate — blocks the defects that made 0.5.0 untransferable.

Run standalone or via tests/test_repo_hygiene.py:

    python3 scripts/check_repo_hygiene.py

Checks, in order of how much they cost when they fail:

1. No third-party rulebook/adventure material is tracked. The 0.5.0 public
   history carried ~230 MiB of commercial D&D adventure PDFs and extracted
   page images that the repo's MIT/CC-BY licenses did not cover. Only official
   Creative Commons SRD material may be redistributed here (see NOTICE).
2. No tracked file exceeds MAX_TRACKED_BYTES unless explicitly allowlisted,
   so a large binary can never be committed casually again.
3. No generated build artifact (build/, dist/, *.egg-info/) is tracked.

Exit 0 = clean, 1 = violations found (printed to stdout).
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

MAX_TRACKED_BYTES = 5 * 1024 * 1024

# Paths permitted to exceed the size gate. Keep this list short and justified.
SIZE_ALLOWLIST: set[str] = set()

# Tracked-path patterns that indicate non-SRD third-party publications.
FORBIDDEN_PATH_PATTERNS = [
    (re.compile(r"(^|/)eval/modules(/|$)"),
     "commercial adventure module corpus (quarantined 2026-07-31)"),
    (re.compile(r"\.pdf$", re.I),
     "PDF: source PDFs are fetched via each adapter's fetch.sh, never tracked"),
]

# Titles of commercial publications that must never appear as tracked files.
FORBIDDEN_TITLE_WORDS = [
    "ravenloft", "tomb_of_horrors", "elemental_evil", "white_plume",
    "queen_of_the_spiders", "castle_amber", "borderlands", "barrier_peaks",
    "forbidden_city", "desert_of_desolation",
]

GENERATED_DIR = re.compile(r"^(build|dist)/|(^|/)[^/]+\.egg-info/")


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def main():
    violations = []
    for rel in tracked_files():
        low = rel.lower()

        for pattern, why in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(rel):
                violations.append(f"third-party/binary content: {rel} — {why}")

        for word in FORBIDDEN_TITLE_WORDS:
            if word in low.replace("-", "_"):
                violations.append(
                    f"commercial publication title in tracked path: {rel} "
                    f"(matched {word!r})")

        if GENERATED_DIR.search(rel):
            violations.append(
                f"generated build artifact tracked: {rel} — see .gitignore")

        path = ROOT / rel
        if path.is_file() and rel not in SIZE_ALLOWLIST:
            size = path.stat().st_size
            if size > MAX_TRACKED_BYTES:
                violations.append(
                    f"tracked file exceeds {MAX_TRACKED_BYTES // 1024 // 1024} "
                    f"MiB size gate: {rel} ({size / 1024 / 1024:.1f} MiB)")

    if violations:
        print(f"repo hygiene: {len(violations)} violation(s)\n")
        for v in sorted(set(violations)):
            print(f"  ✗ {v}")
        print("\nSee NOTICE for what may be redistributed here.")
        return 1

    print(f"repo hygiene: clean ({len(tracked_files())} tracked files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
