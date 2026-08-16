"""Everything the public API returns is caller-owned (issue #27).

`AdapterHandle.record()` used to return the engine's live fact dict. A caller
that edited it silently rewrote the source facts the engine goes on to cite:
`creature.stats` for Aboleth would answer "CR 99, XP 999999" and still attach
the SRD citation. A confident wrong answer carrying provenance is the failure
this project exists to prevent, so these are regressions, not hygiene.
"""
import copy
import inspect
import json

import pytest

from srdcheck.access import AdapterHandle, capabilities, load_adapter

CATEGORY = "creature"
NAME = "Aboleth"


@pytest.fixture
def handle():
    return load_adapter("srd-5.2.1")


def _vandalise(obj):
    """Mutate a returned structure as deeply as its shape allows."""
    if isinstance(obj, dict):
        obj["__vandal__"] = "TAMPERED"
        for value in list(obj.values()):
            _vandalise(value)
    elif isinstance(obj, list):
        for item in list(obj):
            _vandalise(item)
        obj.append("__vandal__")


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def test_a_mutated_record_cannot_change_a_later_verdict(handle):
    """The regression that matters: public mutation reaching a cited verdict."""
    before = handle.query("creature.stats", {"name": NAME})
    record = handle.record(CATEGORY, NAME)
    record["cr"] = "99"
    record["xp"] = 999999
    after = handle.query("creature.stats", {"name": NAME})
    assert after["why"] == before["why"]
    assert "99" not in after["why"]


def test_record_is_not_the_live_internal_dict(handle):
    first = handle.record(CATEGORY, NAME)
    first["cr"] = "TAMPERED"
    assert handle.record(CATEGORY, NAME)["cr"] != "TAMPERED"


def test_record_returns_none_without_copying_nothing(handle):
    assert handle.record(CATEGORY, "Definitely Not A Creature") is None


def test_manifest_is_copied_through_nested_objects(handle):
    """A shallow dict() left `source` — the provenance sha256 — writable."""
    handle.manifest["source"]["sha256"] = "TAMPERED"
    assert handle.manifest["source"]["sha256"] != "TAMPERED"


def test_entities_records_are_copied_not_just_the_list(handle):
    for entry in handle.entities(CATEGORY):
        if isinstance(entry, dict):
            entry["name"] = "TAMPERED"
    assert not any(e.get("name") == "TAMPERED"
                   for e in handle.entities(CATEGORY) if isinstance(e, dict))


def test_two_handles_over_one_adapter_stay_independent():
    a, b = load_adapter("srd-5.2.1"), load_adapter("srd-5.2.1")
    record = a.record(CATEGORY, NAME)
    record["cr"] = "CROSS"
    assert b.record(CATEGORY, NAME)["cr"] != "CROSS"
    assert a.record(CATEGORY, NAME)["cr"] != "CROSS"


def test_capabilities_is_caller_owned():
    _vandalise(capabilities())
    fresh = capabilities()
    assert "__vandal__" not in fresh
    assert "__vandal__" not in fresh["refusal_contract"]


PUBLIC_READERS = {
    "manifest": (),
    "categories": (),
    "entities": (CATEGORY,),
    "names": (CATEGORY,),
    "record": (CATEGORY, NAME),
    "query_types": (),
}


def test_every_public_reader_is_covered_by_this_file():
    """Fix the class, not the instance: if someone adds a public accessor,
    this fails until it is listed and therefore mutation-tested below."""
    public = {
        name for name, member in inspect.getmembers(AdapterHandle)
        if not name.startswith("_")
        and (inspect.isfunction(member) or isinstance(member, property))
    }
    untested = public - set(PUBLIC_READERS) - {"query", "id", "name", "version"}
    assert untested == set(), f"public accessors with no ownership test: {untested}"


@pytest.mark.parametrize("accessor", sorted(PUBLIC_READERS))
def test_public_reader_hands_out_caller_owned_data(handle, accessor):
    """Call it, vandalise whatever comes back as deeply as its shape allows,
    then prove a fresh call is untouched."""
    member = getattr(type(handle), accessor, None)
    call = (lambda: getattr(handle, accessor)) if isinstance(member, property) \
        else (lambda: getattr(handle, accessor)(*PUBLIC_READERS[accessor]))

    baseline = _canonical(call())
    _vandalise(call())
    assert _canonical(call()) == baseline, f"{accessor}() leaked internal state"


def test_verdicts_are_unaffected_after_vandalising_every_reader(handle):
    """The end-to-end property: nothing a caller does through the public API
    can move a verdict."""
    before = {q: handle.query(q, p) for q, p in (
        ("creature.stats", {"name": NAME}),
        ("creature.valid", {"name": NAME}),
        ("jurisdiction", {"name": NAME}),
    )}
    for accessor, args in PUBLIC_READERS.items():
        member = getattr(type(handle), accessor, None)
        value = getattr(handle, accessor) if isinstance(member, property) \
            else getattr(handle, accessor)(*args)
        _vandalise(value)
    after = {q: handle.query(q, p) for q, p in (
        ("creature.stats", {"name": NAME}),
        ("creature.valid", {"name": NAME}),
        ("jurisdiction", {"name": NAME}),
    )}
    assert after == before


def test_copy_overhead_stays_proportionate(handle):
    """#27 asks for the overhead to be measured, not assumed. entities() is a
    discovery surface off the query path; this pins it to the same order of
    magnitude as a query rather than an arbitrary wall-clock number."""
    import timeit
    biggest = max(handle.categories(), key=lambda c: len(handle.entities(c)))
    entities = timeit.timeit(lambda: handle.entities(biggest), number=50) / 50
    query = timeit.timeit(
        lambda: handle.query("creature.stats", {"name": NAME}), number=50) / 50
    assert entities < query * 100, (
        f"entities({biggest!r}) at {entities*1e6:.0f}us vs query "
        f"{query*1e6:.0f}us — copy overhead has become disproportionate")


def test_internal_surfaces_deliberately_do_not_copy(handle):
    """The other half of the ownership rule. Adapter.entity_record is the hot
    path handlers read; it stays shared and read-only by contract. If this
    ever starts copying, the public boundary above is redundant overhead."""
    adapter = handle._a
    assert adapter.entity_record(CATEGORY, NAME) is adapter.entity_record(
        CATEGORY, NAME)
