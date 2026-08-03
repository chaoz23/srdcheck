"""Declared JSON Schemas are enforced before handler dispatch."""

import json
import math
import pathlib
import subprocess
import sys

import pytest

from srdcheck.engine import Engine
from srdcheck.schema import errors, issues as schema_issues, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])
TOY = Engine([ROOT / "srdcheck" / "adapters" / "toy-tictactoe"])


def invalid(query, params, fragment):
    verdict = E.query(query, params)
    assert verdict.exit_code == 2
    assert fragment in " ".join(verdict.data["validation_errors"])
    return verdict


def test_required_and_top_level_type_are_enforced():
    invalid("turn.plan", {}, "$.speed: required")
    invalid("turn.plan", [], "$: expected object")


def test_scalar_types_do_not_coerce_and_bool_is_not_integer():
    invalid("turn.plan", {"speed": "30", "plan": []}, "$.speed: expected integer")
    invalid("turn.plan", {"speed": True, "plan": []}, "$.speed: expected integer")
    assert E.query("turn.plan", {"speed": 30.0, "plan": []}).exit_code == 0


def test_integer_normalization_is_recursive_and_never_mutates_the_request():
    schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "nested": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "value": {"type": "integer"},
                    "measurement": {"type": "number"},
                }},
            },
        },
    }
    supplied = {
        "count": 1.0,
        "nested": [{"value": 2.0, "measurement": 3.0}],
    }

    normalized = validate(supplied, schema)

    assert normalized == {
        "count": 1,
        "nested": [{"value": 2, "measurement": 3.0}],
    }
    assert isinstance(normalized["count"], int)
    assert isinstance(normalized["nested"][0]["value"], int)
    assert isinstance(normalized["nested"][0]["measurement"], float)
    assert supplied["count"] == 1.0 and isinstance(supplied["count"], float)
    assert normalized is not supplied and normalized["nested"] is not supplied["nested"]


def _integer_paths(schema, prefix=()):
    if not isinstance(schema, dict):
        return []
    expected = schema.get("type")
    choices = expected if isinstance(expected, list) else [expected]
    found = [prefix] if "integer" in choices else []
    for name, child in schema.get("properties", {}).items():
        found.extend(_integer_paths(child, prefix + (name,)))
    if isinstance(schema.get("items"), dict):
        found.extend(_integer_paths(schema["items"], prefix + (None,)))
    if isinstance(schema.get("additionalProperties"), dict):
        found.extend(_integer_paths(
            schema["additionalProperties"], prefix + ("*",)))
    return found


def _integer_sample(schema):
    value = max(1, schema.get("minimum", 1))
    if "maximum" in schema:
        value = min(value, schema["maximum"])
    return int(value)


def _materialize(schema, target=None, integral_float=False):
    if not isinstance(schema, dict):
        return None
    if target == ():
        value = _integer_sample(schema)
        return float(value) if integral_float else value
    if "enum" in schema and target is None:
        return schema["enum"][0]
    expected = schema.get("type")
    if expected == "object":
        properties = schema.get("properties", {})
        wanted = target[0] if target else None
        result = {}
        for name in schema.get("required", []):
            child_target = target[1:] if target and name == wanted else None
            result[name] = _materialize(
                properties.get(name, {}), child_target, integral_float)
        if wanted is not None and wanted not in result and wanted in properties:
            result[wanted] = _materialize(
                properties[wanted], target[1:], integral_float)
        return result
    if expected == "array":
        if target:
            return [_materialize(
                schema.get("items", {}), target[1:], integral_float)]
        return [_materialize(schema.get("items", {}))
                for _ in range(schema.get("minItems", 0))]
    if expected == "string":
        length = max(1, schema.get("minLength", 1))
        if "maxLength" in schema:
            length = min(length, schema["maxLength"])
        return "x" * length
    if expected == "boolean":
        return False
    if expected == "number":
        return 1
    if expected == "integer":
        return _integer_sample(schema)
    if "enum" in schema:
        return schema["enum"][0]
    return None


def _at_path(value, path):
    for part in path:
        value = value[0] if part is None else value[part]
    return value


def _path_label(path):
    label = ""
    for part in path:
        label += "[]" if part is None else ("." if label else "") + part
    return label


def test_every_bundled_query_integer_reaches_handlers_as_canonical_int(monkeypatch):
    """Parity ratchet: inventory every integer schema leaf before dispatch."""
    engines = (E, TOY)
    inventoried = []
    for engine in engines:
        adapter = engine.adapters[0]

        def capture(query_type, params):
            return params

        monkeypatch.setattr(adapter, "handle", capture)
        for query_type, meta in adapter.query_meta.items():
            schema = meta["inputSchema"]
            for path in _integer_paths(schema):
                integer_request = _materialize(schema, path)
                float_request = _materialize(schema, path, integral_float=True)
                assert schema_issues(integer_request, schema) == []
                assert schema_issues(float_request, schema) == []

                integer_dispatched = engine.query(query_type, integer_request)
                float_dispatched = engine.query(query_type, float_request)

                assert _at_path(integer_dispatched, path) == _at_path(
                    float_dispatched, path)
                assert isinstance(_at_path(float_dispatched, path), int)
                assert isinstance(_at_path(float_request, path), float)
                inventoried.append(
                    f"{adapter.manifest['name']}/{query_type}:{_path_label(path)}")

    assert set(inventoried) == {
        "srd-5.2.1/turn.plan:speed",
        "srd-5.2.1/turn.plan:exhaustion_level",
        "srd-5.2.1/turn.plan:spent.movement_ft",
        "srd-5.2.1/turn.plan:spent.spell_slots_this_turn",
        "srd-5.2.1/turn.plan:plan[].feet",
        "srd-5.2.1/turn.plan:plan[].spell.level",
        "srd-5.2.1/turn.options:speed",
        "srd-5.2.1/turn.options:exhaustion_level",
        "srd-5.2.1/attack.modifiers:attacker.exhaustion_level",
        "srd-5.2.1/attack.modifiers:distance_ft",
        "srd-5.2.1/event.apply:event.feet",
        "srd-5.2.1/event.apply:event.spell.level",
        "srd-5.2.1/event.apply:event.amount",
        "srd-5.2.1/event.apply:event.result",
        "srd-5.2.1/encounter.xp-budget:level",
        "srd-5.2.1/encounter.xp-budget:party_size",
        "srd-5.2.1/save.check:dc",
        "srd-5.2.1/save.check:d20_result",
        "srd-5.2.1/save.check:modifier",
        "srd-5.2.1/save.check:exhaustion_level",
        "srd-5.2.1/check.make:dc",
        "srd-5.2.1/check.make:d20_result",
        "srd-5.2.1/check.make:modifier",
        "srd-5.2.1/check.make:exhaustion_level",
        "srd-5.2.1/concentration.check:damage",
        "srd-5.2.1/concentration.check:d20_result",
        "srd-5.2.1/concentration.check:con_modifier",
        "srd-5.2.1/grapple.initiate:str_modifier",
        "srd-5.2.1/grapple.initiate:proficiency_bonus",
        "srd-5.2.1/passive.perception:perception_modifier",
        "srd-5.2.1/feature.uses:charisma_modifier",
        "srd-5.2.1/feature.uses:paladin_level",
        "toy-tictactoe/ttt.move:cell",
    }


def test_enum_and_numeric_bounds_are_enforced():
    invalid("encounter.xp-budget", {"level": 0, "difficulty": "low"}, ">= 1")
    invalid("grapple.initiate", {"kind": "trip"}, "expected one of")


def test_nested_required_unknown_and_array_item_types_are_enforced():
    invalid("turn.plan", {"speed": 30, "plan": [{}]}, "$.plan[0].do: required")
    invalid("turn.plan", {"speed": 30, "plan": [{"do": "move", "bogus": 1}]},
            "$.plan[0].bogus: field is not allowed")
    invalid("turn.plan", {"speed": 30, "conditions": [3], "plan": []},
            "$.conditions[0]: expected string")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_refuse(value):
    invalid("mage-hand.use", {"kind": "attack", "weight_lb": value},
            "expected number")


@pytest.mark.parametrize("value", [1.5, True, math.nan, math.inf, -math.inf, "1"])
def test_integer_representations_outside_json_schema_semantics_refuse(value):
    result = invalid(
        "encounter.xp-budget", {"level": value, "difficulty": "low"},
        "$.level: expected integer")
    assert result.data["reason_code"] == "invalid-input"
    assert result.data["missing_inputs"] == []


@pytest.mark.parametrize("value", [-(10 ** 1_000), 10 ** 1_000])
def test_extreme_integers_refuse_without_overflow(value):
    invalid("encounter.xp-budget", {"level": value, "difficulty": "low"},
            "must be")


def test_oversized_and_deeply_malformed_payloads_stop_before_dispatch(monkeypatch):
    def must_not_run(*_args):
        raise AssertionError("handler ran after schema validation failed")

    monkeypatch.setattr(E.adapters[0], "handle", must_not_run)
    result = E.query("turn.plan", {
        "speed": 30,
        "conditions": [0] * 10_000,
        "plan": [],
    })
    assert result.exit_code == 2
    assert len(result.data["validation_errors"]) == 50

    deep = None
    for _ in range(1_000):
        deep = {"nested": deep}
    result = E.query("turn.plan", {
        "speed": 30,
        "plan": [{"do": "action", "spell": {"level": deep}}],
    })
    assert result.exit_code == 2
    assert "$.plan[0].spell.level: expected integer" in result.data[
        "validation_errors"]


def test_string_length_and_malformed_nesting_are_enforced():
    result = TOY.query("ttt.move", {"board": "." * 10_000, "player": "X", "cell": 1})
    assert result.exit_code == 2
    assert "length must be at most 9" in result.data["validation_errors"][0]
    invalid("turn.plan", {"speed": 30, "plan": ["action"]},
            "$.plan[0]: expected object")


def test_array_cardinality_bounds_are_enforced():
    schema = {
        "type": "array", "items": {"type": "integer"},
        "minItems": 2, "maxItems": 3,
    }
    assert errors([1], schema) == ["$: must contain at least 2 items"]
    assert errors([1, 2, 3, 4], schema) == ["$: must contain at most 3 items"]


def test_declared_schema_keyword_set_is_fully_supported():
    supported = {
        "type", "properties", "required", "additionalProperties", "items",
        "enum", "minimum", "maximum", "minItems", "maxItems", "minLength",
        "maxLength", "description", "title", "default", "const", "allOf",
        "if", "then", "else",
    }
    seen = set()

    def walk(schema):
        seen.update(schema)
        for child in schema.get("properties", {}).values():
            walk(child)
        if isinstance(schema.get("items"), dict):
            walk(schema["items"])
        if isinstance(schema.get("additionalProperties"), dict):
            walk(schema["additionalProperties"])
        for child in schema.get("allOf", []):
            walk(child)
        for keyword in ("if", "then", "else"):
            if isinstance(schema.get(keyword), dict):
                walk(schema[keyword])

    for adapter in E.adapters + TOY.adapters:
        for meta in adapter.query_meta.values():
            walk(meta["inputSchema"])
    assert seen <= supported


@pytest.mark.parametrize("bad", [None, True, 1.5, "30", [], {}])
def test_wrong_type_corpus_is_rejected_deterministically(bad):
    first = E.query("turn.plan", {"speed": bad, "plan": []})
    second = E.query("turn.plan", {"speed": bad, "plan": []})
    assert first.exit_code == second.exit_code == 2
    assert first.data["validation_errors"] == second.data["validation_errors"]


@pytest.mark.parametrize("payload, fragment", [
    ("[]", "$: expected object"),
    ('{"params": {}}', "$.type: required"),
    ('{"type": 3, "params": {}}', "$.type: expected string"),
    ('{"type": "turn.plan", "params": [], "extra": true}',
     "$.params: expected object"),
])
def test_pipe_transport_validates_its_envelope(payload, fragment):
    result = subprocess.run(
        [sys.executable, "-m", "srdcheck", "--pipe"],
        input=payload, text=True, capture_output=True, cwd=ROOT, timeout=30,
    )
    body = json.loads(result.stdout)
    assert result.returncode == body["exit_code"] == 2
    assert fragment in " ".join(body["data"]["validation_errors"])


def test_cli_and_pipe_share_integer_normalization_semantics():
    direct = E.query("encounter.xp-budget", {
        "level": 1, "difficulty": "low", "party_size": 4,
    }).as_dict()
    query = subprocess.run(
        [sys.executable, "-m", "srdcheck", "query", "encounter.xp-budget",
         '{"level":1.0,"difficulty":"low","party_size":4.0}'],
        text=True, capture_output=True, cwd=ROOT, timeout=30,
    )
    pipe = subprocess.run(
        [sys.executable, "-m", "srdcheck", "--pipe"],
        input=json.dumps({
            "type": "encounter.xp-budget",
            "params": {"level": 1.0, "difficulty": "low", "party_size": 4.0},
        }),
        text=True, capture_output=True, cwd=ROOT, timeout=30,
    )

    assert query.returncode == pipe.returncode == 0
    assert json.loads(query.stdout) == json.loads(pipe.stdout) == direct


def test_valid_boundaries_reach_handlers():
    assert E.query("encounter.xp-budget", {"level": 1, "difficulty": "low"}).exit_code == 0
    assert E.query("turn.plan", {"speed": 0, "plan": []}).exit_code == 0
