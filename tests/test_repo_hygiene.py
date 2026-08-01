"""No unlicensed third-party material, large binary, or build artifact may be
tracked. Enforces scripts/check_repo_hygiene.py in CI.

Context: the public repository carried ~230 MiB of commercial D&D adventure
PDFs and extracted page images under licenses that covered neither. They were
quarantined on 2026-07-31; this test stops them coming back.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_repo_hygiene_gate_passes():
    proc = subprocess.run(
        [sys.executable, "scripts/check_repo_hygiene.py"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_no_commercial_adventure_material_tracked():
    """Named publications that must never reappear in tracked paths."""
    from scripts.check_repo_hygiene import FORBIDDEN_TITLE_WORDS, tracked_files
    tracked = [p.lower().replace("-", "_") for p in tracked_files()]
    for word in FORBIDDEN_TITLE_WORDS:
        offenders = [p for p in tracked if word in p]
        assert not offenders, f"commercial material tracked: {offenders}"


def test_only_srd_pdfs_are_ever_untracked_sources():
    from scripts.check_repo_hygiene import tracked_files
    assert not [p for p in tracked_files() if p.lower().endswith(".pdf")], (
        "PDFs must be fetched via each adapter's hash-pinned fetch.sh")


def test_no_generated_build_artifacts_tracked():
    from scripts.check_repo_hygiene import GENERATED_DIR, tracked_files
    offenders = [p for p in tracked_files() if GENERATED_DIR.search(p)]
    assert not offenders, f"generated artifacts tracked: {offenders[:5]}"
