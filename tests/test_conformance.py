"""E2: every bundled adapter must clear the same bar we ask of third parties."""
import json
import pathlib

import pytest
from srdcheck import cli
import srdcheck.access as access
from srdcheck.access import available_adapters
from srdcheck.conformance import check
from srdcheck.scaffold import new_adapter


@pytest.mark.parametrize("aid", available_adapters())
def test_bundled_adapters_conform(aid):
    assert check(aid) == []


def test_scaffold_creates_skeleton(tmp_path):
    d = pathlib.Path(new_adapter("example-rules", str(tmp_path)))
    assert (d / "manifest.json").exists() and (d / "handlers.py").exists()
    q = json.load(open(d / "queries.json"))
    assert all(s["inputSchema"]["additionalProperties"] is False for s in q.values())


def test_conformance_checks_the_supplied_adapter_root(tmp_path):
    """A third-party root must not fall back to a bundled adapter by id."""
    d = pathlib.Path(new_adapter("external-rules", str(tmp_path)))
    (d / "entities.json").write_text(json.dumps({
        "role": ["Guide"],
        "title": ["Guide"],
    }))
    assert check("external-rules", tmp_path) == []


@pytest.mark.parametrize("payload,problem", [
    (b'{"name":', "manifest.json is not valid JSON"),
    (b'\xff', "manifest.json is not valid UTF-8"),
    (b'[]', "manifest.json root must be an object; got array"),
    (b'"adapter"', "manifest.json root must be an object; got string"),
    (b'null', "manifest.json root must be an object; got null"),
])
def test_malformed_manifest_returns_one_fatal_finding(
        tmp_path, monkeypatch, payload, problem):
    adapter = tmp_path / "broken-rules"
    adapter.mkdir()
    (adapter / "manifest.json").write_bytes(payload)

    class MustNotLoad:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("fatal manifest must stop before adapter load")

    monkeypatch.setattr("srdcheck.engine.Engine", MustNotLoad)
    assert check(adapter.name, tmp_path) == [problem]


def test_manifest_read_failure_returns_finding(tmp_path, monkeypatch):
    adapter = tmp_path / "unreadable-rules"
    adapter.mkdir()
    manifest = adapter / "manifest.json"
    manifest.write_text("{}")
    original = pathlib.Path.read_bytes

    def fail_manifest_read(path):
        if path == manifest:
            raise OSError("platform-specific private detail")
        return original(path)

    monkeypatch.setattr(pathlib.Path, "read_bytes", fail_manifest_read)
    assert check(adapter.name, tmp_path) == ["could not read manifest.json"]


def test_missing_manifest_returns_finding_without_loading(tmp_path, monkeypatch):
    adapter = tmp_path / "missing-rules"
    adapter.mkdir()

    class MustNotLoad:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("missing manifest must stop before adapter load")

    monkeypatch.setattr("srdcheck.engine.Engine", MustNotLoad)
    assert check(adapter.name, tmp_path) == ["missing manifest.json"]


@pytest.mark.parametrize("payload,problem", [
    (None, "missing manifest.json"),
    (b'{"name":', "manifest.json is not valid JSON"),
    (b'\xff', "manifest.json is not valid UTF-8"),
    (b'[]', "manifest.json root must be an object; got array"),
    (b'"adapter"', "manifest.json root must be an object; got string"),
    (b'null', "manifest.json root must be an object; got null"),
])
def test_cli_conformance_reports_malformed_manifest_without_traceback(
        tmp_path, monkeypatch, capsys, payload, problem):
    adapter = tmp_path / "broken-rules"
    adapter.mkdir()
    if payload is not None:
        (adapter / "manifest.json").write_bytes(payload)
    monkeypatch.setattr(access, "ADAPTERS_DIR", tmp_path)

    assert cli.main(["conformance", adapter.name]) == 1
    captured = capsys.readouterr()
    response = json.loads(captured.out)
    assert response == {"adapter": adapter.name, "problems": [problem],
                        "ok": False}
    assert captured.err == ""
    assert "Traceback" not in captured.out


def test_valid_scaffold_remains_conformant_through_library_and_cli(
        tmp_path, monkeypatch, capsys):
    adapter = pathlib.Path(new_adapter("valid-rules", str(tmp_path)))
    assert check(adapter.name, tmp_path) == []

    monkeypatch.setattr(access, "ADAPTERS_DIR", tmp_path)
    assert cli.main(["conformance", adapter.name]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "adapter": adapter.name, "problems": [], "ok": True,
    }


def test_golden_corpus_holds():
    import subprocess, sys
    r = subprocess.run([sys.executable, "scripts/build_golden.py", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
