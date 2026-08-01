"""Strict adapter version identities and legacy fallback behavior."""

import json
import pathlib

import pytest

import srdcheck.access as access
from srdcheck.adapter import Adapter
from srdcheck.conformance import check
from srdcheck.contract import is_semver_2_0
from srdcheck.scaffold import new_adapter


VERSION_FIELDS = ("version", "data_version", "rules_version")
VALID_VERSIONS = (
    "0.0.0",
    "1.2.3",
    "1.2.3-alpha.1",
    "1.2.3+build.5",
    "1.2.3-rc.1+build.5",
)
INVALID_VERSIONS = (
    pytest.param("", id="empty"),
    pytest.param(7, id="non-string"),
    pytest.param("1.2", id="short"),
    pytest.param("v1.2.3", id="v-prefix"),
    pytest.param("01.2.3", id="leading-zero"),
    pytest.param("1.2.3-01", id="bad-prerelease"),
    pytest.param("1.2.3+build..1", id="bad-build"),
)


def _scaffold(tmp_path, name="versioned-rules"):
    return pathlib.Path(new_adapter(name, str(tmp_path)))


def _read_manifest(root):
    return json.loads((root / "manifest.json").read_text())


def _write_manifest(root, manifest):
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1))


@pytest.mark.parametrize("field", VERSION_FIELDS)
@pytest.mark.parametrize("version", VALID_VERSIONS)
def test_conformance_accepts_semver_2_0_for_every_version_field(
        tmp_path, field, version):
    root = _scaffold(tmp_path)
    manifest = _read_manifest(root)
    manifest[field] = version
    _write_manifest(root, manifest)

    assert check(root.name, tmp_path) == []


@pytest.mark.parametrize("field", VERSION_FIELDS)
@pytest.mark.parametrize("version", INVALID_VERSIONS)
def test_conformance_rejects_invalid_semver_for_every_version_field(
        tmp_path, field, version):
    root = _scaffold(tmp_path)
    manifest = _read_manifest(root)
    manifest[field] = version
    _write_manifest(root, manifest)

    problems = check(root.name, tmp_path)

    assert any(
        f"manifest '{field}' must be a SemVer 2.0 string" in problem
        for problem in problems
    )


@pytest.mark.parametrize(
    "version",
    (
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-01",
        "1.2.3-alpha..1",
        "1.2.3+build..1",
        "1.2.3 ",
        True,
        None,
    ),
)
def test_semver_helper_is_strict_and_fullmatch(version):
    assert not is_semver_2_0(version)


@pytest.mark.parametrize("field", ("data_version", "rules_version"))
def test_explicit_empty_split_version_is_preserved_not_masked(
        tmp_path, monkeypatch, field):
    root = _scaffold(tmp_path)
    manifest = _read_manifest(root)
    manifest["version"] = "9.8.7"
    manifest[field] = ""
    _write_manifest(root, manifest)

    adapter = Adapter(root)
    assert getattr(adapter, field) == ""

    monkeypatch.setattr(access, "ADAPTERS_DIR", tmp_path)
    payload = access.capabilities()
    emitted = next(item for item in payload["adapters"]
                   if item["identifier"] == root.name)
    assert emitted[field] == ""
    assert any(
        f"manifest '{field}' must be a SemVer 2.0 string" in problem
        for problem in check(root.name, tmp_path)
    )


def test_legacy_aggregate_only_manifest_falls_back_and_conforms(
        tmp_path, monkeypatch):
    root = _scaffold(tmp_path)
    manifest = _read_manifest(root)
    manifest["version"] = "2.4.6"
    manifest.pop("data_version")
    manifest.pop("rules_version")
    _write_manifest(root, manifest)

    adapter = Adapter(root)
    assert adapter.data_version == "2.4.6"
    assert adapter.rules_version == "2.4.6"

    monkeypatch.setattr(access, "ADAPTERS_DIR", tmp_path)
    payload = access.capabilities()
    emitted = next(item for item in payload["adapters"]
                   if item["identifier"] == root.name)
    assert emitted["data_version"] == "2.4.6"
    assert emitted["rules_version"] == "2.4.6"
    assert check(root.name, tmp_path) == []


def test_missing_aggregate_version_is_reported_without_crashing(tmp_path):
    root = _scaffold(tmp_path)
    manifest = _read_manifest(root)
    manifest.pop("version")
    _write_manifest(root, manifest)

    problems = check(root.name, tmp_path)

    assert "manifest missing 'version'" in problems
    assert "adapter failed to load (KeyError)" in problems
