"""Declared JSON Schemas are enforced before handler dispatch."""

import json
import math
import pathlib
import subprocess
import sys

import pytest

from srdcheck.engine import Engine
from srdcheck.schema import errors

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
        "maxLength", "description", "title", "default",
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


def test_valid_boundaries_reach_handlers():
    assert E.query("encounter.xp-budget", {"level": 1, "difficulty": "low"}).exit_code == 0
    assert E.query("turn.plan", {"speed": 0, "plan": []}).exit_code == 0
