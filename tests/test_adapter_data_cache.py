"""Adapter-owned data files are cached on the adapter, never on a handler
module (issue #24). A module-level cache is shared by every adapter that
imports the module and outlives all of them, so it cannot be torn down and
cannot be keyed correctly.
"""
import ast
import json
import pathlib

from srdcheck.adapter import Adapter

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "srdcheck" / "adapters"
BUNDLED = ADAPTERS / "srd-5.2.1"


def test_data_is_read_once_per_adapter():
    a = Adapter(BUNDLED)
    first = a.data("state_schema.json")
    second = a.data("state_schema.json")
    assert first is second, "each call re-parsed the file"


def test_two_adapters_do_not_share_a_data_cache():
    a, b = Adapter(BUNDLED), Adapter(BUNDLED)
    assert a.data("spell_facts.json") is not b.data("spell_facts.json")


def test_cache_is_owned_by_the_adapter_instance():
    """Dropping the Adapter is a complete teardown — nothing survives in a
    module namespace to leak into the next one."""
    a = Adapter(BUNDLED)
    a.data("spell_facts.json")
    assert "spell_facts.json" in a._data
    assert Adapter(BUNDLED)._data == {}


def test_event_apply_stops_reparsing_the_state_schema():
    """event.apply read and parsed state_schema.json on every single call."""
    a = Adapter(BUNDLED)
    reads = []
    real = Adapter.data

    def counting(self, filename):
        reads.append(filename)
        return real(self, filename)

    Adapter.data = counting
    try:
        for _ in range(3):
            a.handle("event.apply", {})
    finally:
        Adapter.data = real
    assert reads.count("state_schema.json") <= 1, (
        f"state_schema.json read {reads.count('state_schema.json')} times "
        "across 3 calls")


def test_handler_verdicts_do_not_mutate_cached_adapter_data():
    """The cache hands out a shared object rather than a copy, so a handler
    that mutated it would poison every later verdict."""
    a = Adapter(BUNDLED)
    a.data("spell_facts.json")
    a.data("state_schema.json")
    a.data("condition_dependencies.json")
    before = {k: json.dumps(val, sort_keys=True) for k, val in a._data.items()}
    for query, params in (
            ("spell.facts", {"name": "Mage Hand"}),
            ("spell.facts", {"name": "Bless", "cast_at": 100.0}),
            ("event.apply", {}),
            ("turn.plan", {}),
            ("attack.modifiers", {}),
            ("save.check", {}),
    ):
        a.handle(query, params)
    after = {k: json.dumps(val, sort_keys=True) for k, val in a._data.items()}
    assert after == before


def _module_level_caches(path):
    """Module-level names assigned a mutable-or-None value that some function
    rebinds via `global` — the lazy-cache shape."""
    tree = ast.parse(path.read_text())
    rebound = {name for node in ast.walk(tree)
               if isinstance(node, ast.Global) for name in node.names}
    assigned = {t.id for node in tree.body if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Name)}
    return sorted(rebound & assigned)


def test_no_handler_module_keeps_a_mutable_global_cache():
    """The class, not the instance: any adapter, any module."""
    offenders = {}
    for adapter in sorted(ADAPTERS.iterdir()):
        if not adapter.is_dir():
            continue
        sources = list(adapter.glob("handlers.py"))
        sources += list((adapter / "handlers").glob("*.py"))
        for src in sources:
            found = _module_level_caches(src)
            if found:
                offenders[str(src.relative_to(ADAPTERS))] = found
    assert offenders == {}, f"module-level caches: {offenders}"


def test_the_oracle_would_catch_a_reintroduced_cache(tmp_path):
    """Guard the guard — a test that cannot fail is not a test."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "_CACHE = None\n\n\ndef load(adapter):\n"
        "    global _CACHE\n"
        "    if _CACHE is None:\n"
        "        _CACHE = 1\n"
        "    return _CACHE\n")
    assert _module_level_caches(probe) == ["_CACHE"]
