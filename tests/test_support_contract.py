"""Runtime/platform claims stay synchronized with their CI evidence."""

import importlib.util
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
SUPPORT = (ROOT / "docs/support-matrix.md").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _job(name):
    marker = f"  {name}:\n"
    start = WORKFLOW.index(marker) + len(marker)
    next_job = re.search(r"(?m)^  [a-z][a-z0-9-]*:\n", WORKFLOW[start:])
    end = start + next_job.start() if next_job else len(WORKFLOW)
    return WORKFLOW[start:end]


def _cold_smoke_module():
    path = ROOT / "scripts/cold_artifact_smoke.py"
    spec = importlib.util.spec_from_file_location("cold_artifact_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ubuntu_full_suite_covers_every_supported_python():
    full = _job("test")
    assert "runs-on: ubuntu-latest" in full
    assert "windows-latest" not in full and "macos-latest" not in full
    for version in ("3.10", "3.11", "3.12", "3.13"):
        assert f'"{version}"' in full
        assert f'Programming Language :: Python :: {version}' in PYPROJECT
    assert 'requires-python = ">=3.10"' in PYPROJECT


def test_minimum_runtime_lane_matches_declared_build_floor():
    minimum = _job("minimum-runtime")
    assert 'python-version: "3.10"' in minimum
    assert 'setuptools==83.0.0' in minimum
    assert 'requires = ["setuptools>=83.0.0"]' in PYPROJECT
    assert "--no-deps --no-build-isolation" in minimum
    assert "python scripts/cold_artifact_smoke.py dist" in minimum
    assert "no required third-party runtime packages" in SUPPORT
    assert "setuptools==83.0.0" in SUPPORT
    assert "setuptools==77" not in SUPPORT


def test_platform_smoke_is_representative_not_full_matrix():
    platform = _job("platform-smoke")
    assert "windows-latest" in platform
    assert "macos-latest" in platform
    assert 'python-version: ["3.12"]' in platform
    assert "python -m build --outdir dist" in platform
    assert "python scripts/cold_artifact_smoke.py dist" in platform
    assert "representative smoke lanes, not claims of" in SUPPORT
    assert "full Python-by-OS matrix parity" in SUPPORT


def test_both_distribution_types_are_exercised_at_runtime_edges():
    cold = _job("cold-install")
    assert 'python-version: ["3.10", "3.13"]' in cold
    assert "Build wheel and source distribution" in cold
    assert "python -m build --outdir dist" in cold
    assert "python scripts/cold_artifact_smoke.py dist" in cold
    assert "both wheel and source" in SUPPORT


def test_public_docs_link_to_the_support_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    release = (ROOT / "docs/RELEASE.md").read_text(encoding="utf-8")
    assert "[support matrix](docs/support-matrix.md)" in readme
    assert "[support matrix](docs/support-matrix.md)" in contributing
    assert "[support contract](support-matrix.md)" in release
    for job in ("minimum-runtime", "platform-smoke", "cold-install"):
        assert f"`{job}`" in release
    for platform in ("Ubuntu", "Windows", "macOS"):
        assert f"| {platform} |" in SUPPORT
    for version in ("3.10", "3.11", "3.12", "3.13"):
        assert f"| Python {version} | Supported" in SUPPORT
    assert "CLI" in SUPPORT and "MCP stdio" in SUPPORT
    assert "`srdcheck` console entry" in SUPPORT
    assert "`srdcheck-mcp`" in SUPPORT
    assert "spaces and Unicode" in SUPPORT
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "include docs/support-matrix.md" in manifest


def test_artifact_directory_discovery_is_shell_independent(tmp_path):
    module = _cold_smoke_module()

    dist = tmp_path / "artifacts with spaces Ω"
    dist.mkdir()
    wheel = dist / "srdcheck-0-py3-none-any.whl"
    sdist = dist / "srdcheck-0.tar.gz"
    wheel.touch()
    sdist.touch()
    (dist / "SHA256SUMS").touch()

    assert module.discover_artifacts([dist]) == [wheel.resolve(), sdist.resolve()]


def test_console_entrypoint_paths_are_platform_specific(tmp_path):
    module = _cold_smoke_module()
    posix = module.console_entrypoints(tmp_path, "posix")
    windows = module.console_entrypoints(tmp_path, "nt")
    assert posix == (tmp_path / "bin/srdcheck",
                     tmp_path / "bin/srdcheck-mcp")
    assert windows == (tmp_path / "Scripts/srdcheck.exe",
                       tmp_path / "Scripts/srdcheck-mcp.exe")
