"""Adapters may ship their handlers as one `handlers.py` or as a `handlers/`
package (issue #24). Both layouts must load identically, the choice must not
leak into the kernel, and rule logic must count toward adapter identity
wherever it lives.
"""
import json
import pathlib
import shutil

import pytest

from srdcheck.access import _adapter_digest
from srdcheck.adapter import Adapter

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLED = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"

MANIFEST = {
    "name": "layout-probe", "version": "0.1.0",
    "source": {"title": "none", "sha256": "0" * 64},
    "license": "CC-BY-4.0", "attribution": "none",
    "query_types": ["probe.echo"],
}
QUERIES = {"probe.echo": {"description": "echo", "inputSchema": {
    "type": "object", "properties": {}, "additionalProperties": False}}}
SINGLE = '''
from srdcheck import verdict as v


def echo(adapter, p):
    return v.legal("echo", [], [])


HANDLERS = {"probe.echo": echo}
'''
PKG_INIT = '''
from .leaf import echo

HANDLERS = {"probe.echo": echo}
'''
PKG_LEAF = '''
from srdcheck import verdict as v


def echo(adapter, p):
    return v.legal("echo", [], [])
'''


def _skeleton(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(MANIFEST))
    (root / "entities.json").write_text(json.dumps({"thing": ["Widget"]}))
    (root / "queries.json").write_text(json.dumps(QUERIES))
    (root / "atoms").mkdir(exist_ok=True)
    return root


def _single(root):
    _skeleton(root)
    (root / "handlers.py").write_text(SINGLE)
    return root


def _package(root):
    _skeleton(root)
    pkg = root / "handlers"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text(PKG_INIT)
    (pkg / "leaf.py").write_text(PKG_LEAF)
    return root


def test_single_file_layout_still_loads(tmp_path):
    """The documented simple path third-party adapters ship."""
    a = Adapter(_single(tmp_path / "single"))
    assert a.query_types == {"probe.echo", "jurisdiction"}
    assert a.handle("probe.echo", {}).as_dict()["verdict"] == "legal"


def test_package_layout_loads_and_resolves_relative_imports(tmp_path):
    """`from .leaf import echo` only works if the package is registered in
    sys.modules before exec — the thing that made #24 possible."""
    a = Adapter(_package(tmp_path / "pkg"))
    assert a.query_types == {"probe.echo", "jurisdiction"}
    assert a.handle("probe.echo", {}).as_dict()["verdict"] == "legal"


def test_both_layouts_produce_identical_verdicts(tmp_path):
    single = Adapter(_single(tmp_path / "s")).handle("probe.echo", {}).as_dict()
    package = Adapter(_package(tmp_path / "p")).handle("probe.echo", {}).as_dict()
    assert single == package


def test_a_broken_package_leaves_nothing_half_loaded(tmp_path):
    """A failed load must not park a partial module for the next load to find."""
    import hashlib
    import sys
    root = _skeleton(tmp_path / "broken")
    pkg = root / "handlers"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise RuntimeError('boom')\n")
    tag = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:8]
    name = f"srdcheck_adapter_layout_probe_{tag}"
    with pytest.raises(RuntimeError):
        Adapter(root)
    assert name not in sys.modules


def test_two_roots_of_one_adapter_name_do_not_collide(tmp_path):
    """Same manifest name, different paths, different behaviour — the second
    load must not silently reuse the first's module (guards #26)."""
    a_root = _single(tmp_path / "a")
    b_root = _single(tmp_path / "b")
    (b_root / "handlers.py").write_text(
        SINGLE.replace('v.legal("echo", [], [])', 'v.illegal("echo", [], [])'))
    a = Adapter(a_root)
    b = Adapter(b_root)
    assert a.handle("probe.echo", {}).as_dict()["verdict"] == "legal"
    assert b.handle("probe.echo", {}).as_dict()["verdict"] == "illegal"
    # and the first is still itself after the second loaded
    assert a.handle("probe.echo", {}).as_dict()["verdict"] == "legal"


def test_bundled_adapter_digest_covers_every_handler_module(tmp_path):
    """Rule logic in a handlers/ package counts toward adapter identity. If it
    did not, the game logic could change while the digest stood still."""
    copy = tmp_path / "srd-5.2.1"
    shutil.copytree(BUNDLED, copy)
    before = _adapter_digest(copy)
    target = copy / "handlers" / "checks.py"
    target.write_text(target.read_text() + "\n# provenance probe\n")
    assert _adapter_digest(copy) != before


def test_digest_ignores_bytecode_caches(tmp_path):
    """__pycache__ must never enter adapter identity — it varies by
    interpreter and would make the digest non-reproducible."""
    copy = tmp_path / "srd-5.2.1"
    shutil.copytree(BUNDLED, copy)
    before = _adapter_digest(copy)
    cache = copy / "handlers" / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "checks.cpython-999.pyc").write_bytes(b"\x00\x01junk")
    assert _adapter_digest(copy) == before


def test_bundled_adapters_never_ship_both_layouts():
    """A stale handlers.py beside a handlers/ package is ambiguous — the
    loader prefers the package, so the leftover file would be dead code that
    still looks authoritative. Caught in a real build during #24."""
    adapters = ROOT / "srdcheck" / "adapters"
    both = [d.name for d in adapters.iterdir()
            if d.is_dir() and (d / "handlers.py").exists()
            and (d / "handlers" / "__init__.py").exists()]
    assert both == [], f"adapters shipping both handler layouts: {both}"
