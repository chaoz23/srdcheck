#!/usr/bin/env python3
"""Fail release preparation on a dirty checkout or mismatched version tag."""

import argparse
import os
import pathlib
import re
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[1]


def engine_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("project.version is missing from pyproject.toml")
    return match.group(1)


def release_tag():
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        return os.environ.get("GITHUB_REF_NAME")
    return None


def verify_tag(tag, version):
    expected = f"v{version}"
    if tag and tag != expected:
        raise SystemExit(f"release tag {tag!r} does not match {expected!r}")


def verify_clean():
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    if result.stdout:
        raise SystemExit("release source checkout is dirty")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="release tag; defaults to GitHub tag context")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    version = engine_version()
    verify_tag(args.tag or release_tag(), version)
    if args.require_clean:
        verify_clean()
    print(f"release identity: OK v{version}")


if __name__ == "__main__":
    main()
