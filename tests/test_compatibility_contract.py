"""Executable semantic compatibility and correction policy (#29)."""

import json
import pathlib

import srdcheck
from srdcheck import legal, load_adapter
from srdcheck.cli import SCHEMA
from srdcheck.contract import (CAPABILITIES_SCHEMA_VERSION,
                               CORRECTIONS_SCHEMA_VERSION,
                               VERDICT_SCHEMA_VERSION,
                               supported_engine_minors)
from srdcheck.verdict import VERDICT_OUTPUT_SCHEMA


ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPAT = ROOT / "tests" / "compat"


def _assert_subset(expected, actual, path="data"):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected object, got {actual!r}"
        for key, value in expected.items():
            assert key in actual, f"{path}: missing {key!r}"
            _assert_subset(value, actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert expected == actual, f"{path}: {actual!r} != {expected!r}"
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def _current_adapter_for_historical_tuple(historical_adapter):
    """Use the ruleset identifier; retain its old version as provenance only."""
    identifier, historical_version = historical_adapter.split("@", 1)
    assert historical_version
    return load_adapter(identifier)


def test_verdict_schema_is_explicit_without_changing_v051_instances():
    assert VERDICT_OUTPUT_SCHEMA["x-srdcheck-schema-version"] == VERDICT_SCHEMA_VERSION
    assert SCHEMA["schema_version"] == VERDICT_SCHEMA_VERSION
    assert "schema_version" not in legal("wording may improve").as_dict()
    caps = srdcheck.capabilities()
    assert caps["schema_version"] == CAPABILITIES_SCHEMA_VERSION
    assert caps["machine_contracts"]["verdict_schema_version"] == VERDICT_SCHEMA_VERSION


def test_verdict_schema_v1_top_level_and_existing_fields_are_frozen():
    baseline = json.loads((COMPAT / "verdict-schema-1.0.json").read_text())
    current = VERDICT_OUTPUT_SCHEMA
    assert current["x-srdcheck-schema-version"] == baseline[
        "x-srdcheck-schema-version"]
    assert current["type"] == baseline["type"]
    assert current["additionalProperties"] == baseline["additionalProperties"]
    assert set(current["required"]) == set(baseline["required"])
    assert set(current["properties"]) == set(baseline["properties"]), (
        "verdict schema 1.0 forbids unknown top-level fields, so even a new "
        "optional top-level property requires a new schema identity and migration")
    for name, schema in baseline["properties"].items():
        assert current["properties"].get(name) == schema, (
            f"verdict schema 1.0 changed existing field {name!r}; publish a new "
            "schema version and migration instead")


def _assert_shape(name, value, shape):
    expected_types = {
        "string": str, "object": dict, "array": list, "boolean": bool}
    for field, expected in shape.items():
        assert field in value, f"{name}: removed versioned field {field!r}"
        assert isinstance(value[field], expected_types[expected]), (
            f"{name}.{field}: expected {expected}, got {type(value[field]).__name__}")


def test_capabilities_schema_v2_changes_are_additive_only():
    baseline = json.loads((COMPAT / "capabilities-shape-2.0.json").read_text())
    current = srdcheck.capabilities()
    assert current["schema_version"] == baseline["schema_version"]
    _assert_shape("capabilities", current, baseline["top_level"])
    _assert_shape("capabilities.engine", current["engine"], baseline["engine"])
    _assert_shape("capabilities.machine_contracts",
                  current["machine_contracts"], baseline["machine_contracts"])
    _assert_shape("capabilities.release_tuple", current["release_tuple"],
                  baseline["release_tuple"])
    _assert_shape("capabilities.result_contract", current["result_contract"],
                  baseline["result_contract"])
    assert current["adapters"]
    for item in current["adapters"]:
        _assert_shape("capabilities.adapters[]", item, baseline["adapter_item"])
    assert current["release_tuple"]["adapters"]
    for item in current["release_tuple"]["adapters"]:
        _assert_shape("capabilities.release_tuple.adapters[]", item,
                      baseline["release_adapter_item"])
    for item in current["query_coverage"]:
        _assert_shape("capabilities.query_coverage[]", item,
                      baseline["coverage_item"])
    for item in current["targets"]:
        _assert_shape("capabilities.targets[]", item, baseline["target_item"])


def test_capabilities_schema_1_to_2_migration_is_authentic_and_explicit():
    v1 = json.loads((COMPAT / "capabilities-shape-1.0.json").read_text())
    v2 = json.loads((COMPAT / "capabilities-shape-2.0.json").read_text())
    assert v1["source_engine_version"] == "0.5.1"
    assert v1["schema_version"] == "1.0"
    assert v2["schema_version"] == "2.0"
    assert set(v1["top_level"]) < set(v2["top_level"])
    for field, kind in v1["top_level"].items():
        assert v2["top_level"][field] == kind
    for field, kind in v1["adapter_item"].items():
        assert v2["adapter_item"][field] == kind
    assert set(v2["top_level"]) - set(v1["top_level"]) == {
        "machine_contracts", "release_tuple", "result_contract",
        "query_coverage", "targets"}


def test_previous_minor_semantic_fixture():
    fixture = json.loads((COMPAT / "semantic-v0.5.json").read_text())
    assert fixture["source_engine_minor"] == supported_engine_minors(
        srdcheck.__version__)[1]
    assert fixture["excluded_non_contractual_fields"] == ["why"]
    assert all("why" not in case["expected"] for case in fixture["cases"])
    adapter = _current_adapter_for_historical_tuple(fixture["source_adapter"])
    assert adapter.name == fixture["source_adapter"].split("@", 1)[0]
    source_query_types = set(fixture["source_query_types"])
    fixture_query_types = {case["query_type"] for case in fixture["cases"]}
    assert fixture_query_types == source_query_types
    assert source_query_types <= set(adapter.query_types())
    for case in fixture["cases"]:
        result = adapter.query(case["query_type"], case["params"])
        expected = case["expected"]
        assert result["verdict"] == expected["verdict"], case["id"]
        assert result["exit_code"] == expected["exit_code"], case["id"]
        assert result["rule_ids"] == expected["rule_ids"], case["id"]
        citation_identity = [
            {key: citation[key] for key in ("section", "page")
             if key in citation}
            for citation in result["citations"]
        ]
        assert citation_identity == expected["citation_identity"], case["id"]
        if "data_subset" in expected:
            _assert_subset(expected["data_subset"], result.get("data"), case["id"])


def test_historical_adapter_version_does_not_pin_current_adapter():
    adapter = _current_adapter_for_historical_tuple("srd-5.2.1@999.0.0")
    assert adapter.name == "srd-5.2.1"
    assert adapter.id != "srd-5.2.1@999.0.0"


def test_why_is_not_part_of_semantic_compatibility():
    first = legal("first explanation", rule_ids=("contract.example",)).as_dict()
    second = legal("clearer explanation", rule_ids=("contract.example",)).as_dict()
    first.pop("why")
    second.pop("why")
    assert first == second


def test_correction_registry_requires_public_notice_for_high_severity():
    registry = json.loads((ROOT / "docs/ruling-corrections.json").read_text())
    assert registry["schema_version"] == CORRECTIONS_SCHEMA_VERSION
    assert registry["corrections"]
    live_caps = srdcheck.capabilities()
    live_adapters = {item["identifier"]: item
                     for item in live_caps["release_tuple"]["adapters"]}
    ids = []
    for correction in registry["corrections"]:
        ids.append(correction["id"])
        assert correction["severity"] in {"low", "moderate", "high", "critical"}
        assert correction["adapter_identifier"]
        assert correction["affected_query_types"]
        assert correction["affected_rule_ids"]
        corrected = correction["corrected_in"]
        assert set(corrected) == {"engine_version", "adapter_version",
                                  "data_version", "rules_version"}
        assert all(corrected.values())
        assert correction["migration_note"]
        if corrected["engine_version"] == srdcheck.__version__:
            live = live_adapters[correction["adapter_identifier"]]
            assert corrected["adapter_version"] == live["version"]
            assert corrected["data_version"] == live["data_version"]
            assert corrected["rules_version"] == live["rules_version"]
        if correction["severity"] in {"high", "critical"}:
            for field in ("public_notice", "caller_action"):
                assert correction.get(field), (
                    f"{correction['id']}: {field} required for high-severity correction")
    assert len(ids) == len(set(ids))


def test_prose_contract_does_not_invent_per_result_schema_field():
    prose = srdcheck.capabilities()["result_contract"]["prose_stability"]
    assert "obtain the verdict schema identity" in prose
    assert "branch on schema_version" not in prose
