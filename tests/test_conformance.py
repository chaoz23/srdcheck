"""E2: every bundled adapter must clear the same bar we ask of third parties."""
import pytest
from srdcheck.access import available_adapters
from srdcheck.conformance import check


@pytest.mark.parametrize("aid", available_adapters())
def test_bundled_adapters_conform(aid):
    assert check(aid) == []


def test_scaffold_creates_skeleton(tmp_path):
    from srdcheck.scaffold import new_adapter
    import json, pathlib
    d = pathlib.Path(new_adapter("example-rules", str(tmp_path)))
    assert (d / "manifest.json").exists() and (d / "handlers.py").exists()
    q = json.load(open(d / "queries.json"))
    assert all(s["inputSchema"]["additionalProperties"] is False for s in q.values())


def test_golden_corpus_holds():
    import subprocess, sys
    r = subprocess.run([sys.executable, "scripts/build_golden.py", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
