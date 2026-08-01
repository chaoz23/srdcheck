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

    posix_dir = tmp_path / "posix/bin"
    posix_dir.mkdir(parents=True)
    for name in ("srdcheck", "srdcheck-mcp"):
        (posix_dir / name).touch()
    assert module.console_entrypoints(tmp_path / "posix", "posix") == (
        posix_dir / "srdcheck", posix_dir / "srdcheck-mcp")

    windows_scripts = tmp_path / "windows-preferred/Scripts"
    windows_scripts.mkdir(parents=True)
    for name in ("srdcheck.exe", "srdcheck-mcp.exe"):
        (windows_scripts / name).touch()
    assert module.console_entrypoints(tmp_path / "windows-preferred", "nt") == (
        windows_scripts / "srdcheck.exe",
        windows_scripts / "srdcheck-mcp.exe")

    # Hosted Windows exposed this alternate home-scheme layout.
    windows_bin = tmp_path / "windows-home/bin"
    windows_bin.mkdir(parents=True)
    for name in ("srdcheck.exe", "srdcheck-mcp.exe"):
        (windows_bin / name).touch()
    assert module.console_entrypoints(tmp_path / "windows-home", "nt") == (
        windows_bin / "srdcheck.exe", windows_bin / "srdcheck-mcp.exe")


def test_console_entrypoint_discovery_fails_closed(tmp_path):
    module = _cold_smoke_module()
    try:
        module.console_entrypoints(tmp_path, "nt")
    except AssertionError as exc:
        assert "installed srdcheck entry point is missing" in str(exc)
        assert "Scripts" in str(exc) and "bin" in str(exc)
    else:
        raise AssertionError("missing console entry points were accepted")
