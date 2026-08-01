"""The installed artifact must implement the advertised behaviour.

srdcheck 0.5.0's wheel omitted sources/text/page-*.txt because package-data
listed only *.json/*.py/*.md. `srdcheck cite Command` therefore returned
cannot-adjudicate for every user who installed the release, while working
perfectly in the maintainer's prepared checkout — the exact blind spot a
cold-install test exists to close.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import sysconfig
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADAPTERS_WITH_TEXT = ["srd-5.2.1", "srd-5.1"]


def test_source_text_is_present_in_the_checkout():
    """cite() reads these; if extraction never ran, the rest is meaningless."""
    for adapter in ADAPTERS_WITH_TEXT:
        tdir = ROOT / "srdcheck" / "adapters" / adapter / "sources" / "text"
        pages = list(tdir.glob("page-*.txt"))
        assert pages, f"{adapter}: no extracted source text — run sources/extract.py"


def test_package_data_covers_source_text():
    """Fast structural guard: the glob that broke 0.5.0 must stay in place."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "sources/text/*.txt" in text, (
        "package-data no longer ships SRD source text; `cite` will silently "
        "degrade to cannot-adjudicate in installed releases")


def test_notice_declares_redistributed_srd_text():
    """We redistribute CC-BY-4.0 text, which obliges attribution."""
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "CC-BY-4.0" in notice or "Creative Commons Attribution" in notice
    assert "SRD 5.2.1" in notice
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "NOTICE" in text, "NOTICE must ship in distribution metadata"


def _pristine_source_tree(tmp_path):
    """Copy the source tree WITHOUT generated artifacts.

    This is load-bearing. setuptools reuses a stale build/lib/ directory, so a
    wheel built in a working tree that once contained the right files keeps
    shipping them even after package-data stops listing them. That is how
    0.5.0 shipped a wheel missing its source text while building fine on the
    maintainer's machine. Building from a pristine copy reproduces what a
    fresh clone — and CI — would actually produce.
    """
    src = tmp_path / "src"
    ignore = shutil.ignore_patterns(
        "build", "dist", "*.egg-info", "__pycache__", ".git", ".venv")
    shutil.copytree(ROOT, src, ignore=ignore, symlinks=True)
    assert not (src / "build").exists()
    return src


def _build_wheel(tmp_path):
    """Build a wheel from a pristine tree.

    Python 3.12+ venvs ship without setuptools, so --no-isolation can fail with
    a missing backend; fall back to an isolated build, which provisions its own.
    """
    src = _pristine_source_tree(tmp_path)
    outdir = tmp_path / "wheelhouse"
    attempts = [
        [sys.executable, "-m", "build", "--wheel", "--no-isolation",
         "--outdir", str(outdir)],
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir)],
    ]
    errors = []
    for cmd in attempts:
        proc = subprocess.run(cmd, cwd=src, capture_output=True, text=True)
        if proc.returncode == 0:
            wheels = list(outdir.glob("*.whl"))
            assert wheels, "build reported success but produced no wheel"
            return wheels[0]
        errors.append(proc.stderr[-300:])
    pytest.skip("wheel build unavailable: " + " | ".join(errors))


def test_wheel_contains_source_text(tmp_path):
    """The regression gate for the 0.5.0 defect."""
    wheel = _build_wheel(tmp_path)
    names = zipfile.ZipFile(wheel).namelist()
    for adapter in ADAPTERS_WITH_TEXT:
        prefix = f"srdcheck/adapters/{adapter}/sources/text/page-"
        assert any(n.startswith(prefix) and n.endswith(".txt") for n in names), (
            f"wheel omits {adapter} source text — `cite` would return "
            f"cannot-adjudicate for every installed user")
    assert any("NOTICE" in n for n in names), "wheel omits CC-BY NOTICE"


@pytest.mark.slow
def test_cold_installed_wheel_serves_cite(tmp_path):
    """Install into an empty environment and run the headline journeys from
    outside the repo, with no network and no checkout on sys.path."""
    wheel = _build_wheel(tmp_path)

    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    scripts = "Scripts" if sysconfig.get_platform().startswith("win") else "bin"
    python = venv / scripts / ("python.exe" if scripts == "Scripts" else "python")
    pip = venv / scripts / ("pip.exe" if scripts == "Scripts" else "pip")
    subprocess.run([str(pip), "install", "-q", str(wheel)], check=True)

    # cwd is deliberately outside ROOT so the checkout cannot satisfy imports.
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()

    cite = subprocess.run([str(python), "-m", "srdcheck", "cite", "Command"],
                          cwd=workdir, capture_output=True, text=True)
    payload = json.loads(cite.stdout)
    assert cite.returncode == 0, (
        f"installed `cite Command` returned {cite.returncode}: {payload}")
    assert payload["verdict"] != "cannot-adjudicate"
    # cite's provenance surface is the verbatim block itself: a page number and
    # the page's own text. (citations[] carries rule atoms, not source pages.)
    data = payload.get("data") or {}
    assert isinstance(data.get("page"), int), f"cite returned no page: {payload}"
    assert "Command" in data.get("text", ""), "cite returned no source text"

    jur = subprocess.run([str(python), "-m", "srdcheck", "jurisdiction", "Fireball"],
                         cwd=workdir, capture_output=True, text=True)
    assert jur.returncode == 0, jur.stdout + jur.stderr

    ver = subprocess.run(
        [str(python), "-c",
         "import srdcheck,srdcheck.mcp as m;"
         "print(srdcheck.__version__, m.SERVER_INFO['version'])"],
        cwd=workdir, capture_output=True, text=True, check=True)
    installed, served = ver.stdout.split()
    assert installed == served, "installed engine and MCP versions disagree"
