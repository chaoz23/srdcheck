"""Structured exit-2 recovery is machine control flow, never prose parsing."""

import ast
import json
import pathlib

import pytest

from srdcheck import verdict as v
from srdcheck.access import capabilities, edition_check
from srdcheck.engine import Engine, validation_refusal
from srdcheck.schema import ValidationIssue, errors, issues
from srdcheck.scaffold import HANDLERS as SCAFFOLD_HANDLERS
from srdcheck.scaffold import new_adapter


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOY = ROOT / "srdcheck" / "adapters" / "toy-tictactoe"


@pytest.mark.parametrize(
    "reason_code,missing_inputs,recoverability,next_action,authority",
    [
        ("invalid-input", [], "retry", "repair-request", None),
        ("missing-fact", ["actor.ac"], "retry", "provide-facts", None),
        ("unsupported-content", [], "alternate-path", "select-adapter", None),
        ("unmodeled-rule", [], "alternate-path", "use-other-capability", None),
        ("rules-ambiguous", [], "authority", "resolve-table-ruling", "dm"),
        ("gm-discretion", [], "authority", "resolve-table-ruling", "dm"),
    ],
)
def test_reason_codes_derive_canonical_recovery(
        reason_code, missing_inputs, recoverability, next_action, authority):
    result = v.cannot_adjudicate(
        "human explanation can change",
        reason_code=reason_code,
        missing_inputs=missing_inputs,
    )

    assert result.exit_code == v.CANNOT_ADJUDICATE
    assert result.data["reason_code"] == reason_code
    assert result.data["recoverability"] == recoverability
    assert result.data["missing_inputs"] == missing_inputs
    assert result.data["suggested_next_action"] == next_action
    if authority is None:
        assert "required_authority" not in result.data
    else:
        assert result.data["required_authority"] == authority


def test_known_wrong_capability_can_override_unsupported_content_action():
    result = v.cannot_adjudicate(
        "known content, wrong capability",
        reason_code="unsupported-content",
        missing_inputs=[],
        suggested_next_action="use-other-capability",
    )
    assert result.data["suggested_next_action"] == "use-other-capability"


@pytest.mark.parametrize("kwargs", [
    {"reason_code": "missing-fact", "missing_inputs": []},
    {"reason_code": "invalid-input", "missing_inputs": None},
    {"reason_code": "not-a-reason", "missing_inputs": []},
    {"reason_code": "invalid-input", "missing_inputs": [""]},
    {"reason_code": "invalid-input", "missing_inputs": ["x", "x"]},
    {"reason_code": "invalid-input", "missing_inputs": [],
     "suggested_next_action": ""},
    {"reason_code": "gm-discretion", "missing_inputs": [],
     "suggested_next_action": "stop"},
])
def test_incoherent_explicit_recovery_metadata_is_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        v.cannot_adjudicate("bad metadata", **kwargs)


def test_legacy_third_party_call_fails_closed_and_merges_existing_data():
    result = v.cannot_adjudicate(
        "old adapter refusal",
        data={
            "adapter_detail": 7,
            "reason_code": "caller-collision",
            "required_authority": "dm",
        },
    )
    assert result.data == {
        "adapter_detail": 7,
        "reason_code": "unmodeled-rule",
        "recoverability": "terminal",
        "missing_inputs": [],
        "suggested_next_action": "stop",
    }


def test_non_authority_refusal_clears_every_reserved_caller_collision():
    collisions = {
        "reason_code": "gm-discretion",
        "recoverability": "authority",
        "missing_inputs": ["fake"],
        "suggested_next_action": "resolve-table-ruling",
        "required_authority": "dm",
        "adapter_detail": 7,
    }
    result = v.cannot_adjudicate(
        "invalid request", data=collisions,
        reason_code="invalid-input", missing_inputs=[]).data
    assert result == {
        "adapter_detail": 7,
        "reason_code": "invalid-input",
        "recoverability": "retry",
        "missing_inputs": [],
        "suggested_next_action": "repair-request",
    }


def test_legacy_result_mutation_cannot_poison_later_results_or_contract():
    first = v.cannot_adjudicate("first legacy refusal")
    first.data["missing_inputs"].append("caller-mutation")
    second = v.cannot_adjudicate("second legacy refusal")
    assert second.data["missing_inputs"] == []
    assert v.refusal_contract()["legacy_fallback"]["missing_inputs"] == []


def test_contract_accessor_is_machine_readable_and_runtime_is_mutation_safe():
    contract = v.refusal_contract()
    assert contract["schema_version"] == "1.0"
    assert contract["metadata_location"] == "data"
    assert contract["required_fields"] == [
        "reason_code", "recoverability", "missing_inputs",
        "suggested_next_action",
    ]
    assert contract["conditional_fields"]["required_authority"][
        "when_reason_code"] == ["rules-ambiguous", "gm-discretion"]
    json.dumps(contract)

    contract["reason_mappings"]["invalid-input"][
        "suggested_next_action"] = "stop"
    result = v.cannot_adjudicate(
        "still canonical", reason_code="invalid-input", missing_inputs=[])
    assert result.data["suggested_next_action"] == "repair-request"
    assert v.refusal_contract()["reason_mappings"]["invalid-input"][
        "suggested_next_action"] == "repair-request"


def test_published_refusal_contract_is_internally_consistent():
    contract = v.refusal_contract()
    vocab = {key: set(values)
             for key, values in contract["vocabularies"].items()}
    mappings = contract["reason_mappings"]
    assert set(mappings) == vocab["reason_code"]
    for mapping in mappings.values():
        assert mapping["recoverability"] in vocab["recoverability"]
        assert (mapping["suggested_next_action"]
                in vocab["suggested_next_action"])
        if "required_authority" in mapping:
            assert mapping["required_authority"] in vocab[
                "required_authority"]

    authority_reasons = {
        reason for reason, mapping in mappings.items()
        if "required_authority" in mapping
    }
    assert authority_reasons == set(
        contract["conditional_fields"]["required_authority"][
            "when_reason_code"])
    for reason, overrides in contract["allowed_action_overrides"].items():
        assert reason in mappings
        assert set(overrides) <= vocab["suggested_next_action"]
        assert mappings[reason]["suggested_next_action"] not in overrides

    legacy = contract["legacy_fallback"]
    assert legacy["reason_code"] in vocab["reason_code"]
    assert legacy["recoverability"] in vocab["recoverability"]
    assert legacy["suggested_next_action"] in vocab[
        "suggested_next_action"]
    assert legacy["missing_inputs"] == []


def test_capabilities_publish_the_complete_isolated_refusal_contract():
    first = capabilities()
    assert first["machine_contracts"]["refusal_contract_version"] == "1.0"
    assert first["refusal_contract"] == v.refusal_contract()
    first["refusal_contract"]["reason_mappings"]["invalid-input"][
        "suggested_next_action"] = "stop"
    assert capabilities()["refusal_contract"]["reason_mappings"][
        "invalid-input"]["suggested_next_action"] == "repair-request"


def test_every_first_party_refusal_golden_carries_the_contract():
    contract = v.refusal_contract()
    required = set(contract["required_fields"])
    seen = 0
    for path in sorted((ROOT / "tests" / "golden").rglob("*.json")):
        result = json.loads(path.read_text())
        if result["exit_code"] != v.CANNOT_ADJUDICATE:
            continue
        seen += 1
        data = result.get("data", {})
        assert required <= set(data), path
        mapping = contract["reason_mappings"][data["reason_code"]]
        assert data["recoverability"] == mapping["recoverability"], path
        allowed_actions = {
            mapping["suggested_next_action"],
            *contract["allowed_action_overrides"].get(data["reason_code"], []),
        }
        assert data["suggested_next_action"] in allowed_actions, path
        if "required_authority" in mapping:
            assert data["required_authority"] == mapping[
                "required_authority"], path
        else:
            assert "required_authority" not in data, path
    assert seen > 0


def test_verdict_schema_v3_top_level_shape_stays_frozen():
    assert set(v.VERDICT_OUTPUT_SCHEMA["properties"]) == {
        "verdict", "exit_code", "why", "citations", "rule_ids", "adapter",
        "coverage_level", "checked_scope", "unchecked_scope", "assumptions",
        "facts", "rule_result", "table_decision", "state_mutation",
        "explanation", "data",
    }
    assert v.VERDICT_OUTPUT_SCHEMA["properties"]["data"] == {"type": "object"}
    assert "reason_code" not in v.VERDICT_OUTPUT_SCHEMA["properties"]


def test_typed_validation_issues_preserve_the_string_api():
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
        "additionalProperties": False,
    }
    missing = issues({}, schema)
    invalid = issues({"count": "one", "extra": True}, schema)

    assert missing == [ValidationIssue(
        "$.count", "required", "required field is missing")]
    assert [issue.code for issue in invalid] == ["type", "additional-property"]
    assert errors({}, schema) == ["$.count: required field is missing"]
    assert errors({"count": "one", "extra": True}, schema) == [
        "$.count: expected integer",
        "$.extra: field is not allowed",
    ]


def test_validation_classification_uses_issue_codes_not_human_text():
    missing = validation_refusal([
        ValidationIssue("$.actor.ac", "required", "wording without key terms"),
    ])
    invalid = validation_refusal([
        ValidationIssue("$.actor.ac", "type", "required field is missing"),
    ])

    assert missing.data["reason_code"] == "missing-fact"
    assert missing.data["missing_inputs"] == ["actor.ac"]
    assert invalid.data["reason_code"] == "invalid-input"
    assert invalid.data["missing_inputs"] == []


def test_validation_metadata_merges_with_existing_diagnostics():
    engine = Engine([TOY])
    missing = engine.query("ttt.move", {})
    invalid = engine.query("ttt.move", {
        "board": ".........", "player": "X", "cell": "one", "extra": 1,
    })

    assert missing.data["reason_code"] == "missing-fact"
    assert missing.data["missing_inputs"] == ["board", "player", "cell"]
    assert missing.data["validation_errors"]
    assert invalid.data["reason_code"] == "invalid-input"
    assert invalid.data["missing_inputs"] == []
    assert invalid.data["unknown_fields"] == ["extra"]
    assert invalid.data["validation_errors"]


def test_kernel_and_indirect_toy_refusals_keep_structured_recovery():
    engine = Engine([TOY])
    blank_entity = engine.jurisdiction("   ")
    unknown_entity = engine.jurisdiction("not-in-this-game")
    unknown_query = engine.query("unknown.query", {})
    malformed_board = engine.query(
        "ttt.move", {"board": "XO?......", "player": "X", "cell": 3})
    impossible_board = engine.query(
        "ttt.move", {"board": "XX.......", "player": "O", "cell": 3})

    assert blank_entity.data["reason_code"] == "invalid-input"
    assert blank_entity.data["suggested_next_action"] == "repair-request"
    assert unknown_entity.data["reason_code"] == "unsupported-content"
    assert unknown_entity.data["suggested_next_action"] == "select-adapter"
    assert unknown_query.data["reason_code"] == "unmodeled-rule"
    assert unknown_query.data["suggested_next_action"] == "use-other-capability"
    assert malformed_board.data["reason_code"] == "invalid-input"
    assert malformed_board.data["suggested_next_action"] == "repair-request"
    assert impossible_board.data["reason_code"] == "invalid-input"


def test_blank_kernel_selectors_are_repaired_not_routed():
    engine = Engine([TOY])
    blank_query = engine.query("   ", {})
    blank_edition_name = edition_check("   ", "creature")
    blank_edition_category = edition_check("Goblin", "   ")
    for result in (blank_query, blank_edition_name, blank_edition_category):
        assert result.data["reason_code"] == "invalid-input"
        assert result.data["suggested_next_action"] == "repair-request"
        assert result.data["missing_inputs"] == []


def test_loaded_legacy_third_party_adapter_remains_compatible(tmp_path):
    adapter = tmp_path / "legacy-adapter"
    adapter.mkdir()
    (adapter / "atoms").mkdir()
    (adapter / "manifest.json").write_text(json.dumps({
        "name": "legacy", "version": "0.1.0",
    }))
    (adapter / "entities.json").write_text("{}")
    (adapter / "queries.json").write_text(json.dumps({
        "legacy.query": {
            "inputSchema": {"type": "object", "additionalProperties": False},
        },
    }))
    (adapter / "handlers.py").write_text(
        "from srdcheck import verdict as v\n"
        "def legacy(adapter, params):\n"
        "    return v.cannot_adjudicate('legacy refusal', adapter=adapter.id)\n"
        "HANDLERS = {'legacy.query': legacy}\n"
    )

    result = Engine([adapter]).query("legacy.query", {})
    assert result.data["reason_code"] == "unmodeled-rule"
    assert result.data["recoverability"] == "terminal"
    assert result.data["suggested_next_action"] == "stop"


def test_new_adapter_scaffold_emits_explicit_recovery(tmp_path):
    adapter = pathlib.Path(new_adapter("sample-adapter", tmp_path))
    result = Engine([adapter]).query("example.query", {"name": "anything"})
    assert result.data["reason_code"] == "unmodeled-rule"
    assert result.data["recoverability"] == "alternate-path"
    assert result.data["suggested_next_action"] == "use-other-capability"


def _refusal_calls(source):
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        is_refusal = (
            isinstance(function, ast.Name)
            and function.id == "cannot_adjudicate"
        ) or (
            isinstance(function, ast.Attribute)
            and function.attr == "cannot_adjudicate"
        )
        if is_refusal:
            parent = parents.get(node)
            while parent is not None and not isinstance(
                    parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parent = parents.get(parent)
            yield node, (parent.name if parent is not None else None)


_NOT_LITERAL = object()


def _literal(keyword):
    try:
        return ast.literal_eval(keyword.value)
    except (TypeError, ValueError):
        return _NOT_LITERAL


def test_every_first_party_refusal_has_static_classification():
    sources = {
        path.relative_to(ROOT).as_posix(): path.read_text()
        for path in (ROOT / "srdcheck").rglob("*.py")
        if path.name != "verdict.py"
    }
    sources["<new-adapter scaffold handlers>"] = SCAFFOLD_HANDLERS
    failures = []
    contract = v.refusal_contract()
    valid_reasons = set(contract["vocabularies"]["reason_code"])

    for label, source in sources.items():
        for call, function_name in _refusal_calls(source):
            keywords = {kw.arg: kw for kw in call.keywords if kw.arg is not None}
            missing_keywords = {"reason_code", "missing_inputs"} - keywords.keys()
            if missing_keywords:
                failures.append(
                    f"{label}:{call.lineno}: missing {sorted(missing_keywords)}")
                continue
            reason = _literal(keywords["reason_code"])
            dynamic_validation_reason = (
                label == "srdcheck/engine.py"
                and function_name == "validation_refusal"
                and isinstance(keywords["reason_code"].value, ast.Name)
                and keywords["reason_code"].value.id == "reason_code"
            )
            if reason is _NOT_LITERAL and not dynamic_validation_reason:
                failures.append(
                    f"{label}:{call.lineno}: reason_code must be a literal")
                continue
            if reason is not _NOT_LITERAL and reason not in valid_reasons:
                failures.append(
                    f"{label}:{call.lineno}: invalid reason {reason!r}")
                continue
            override = keywords.get("suggested_next_action")
            if override is not None and reason is not _NOT_LITERAL:
                action = _literal(override)
                allowed = set(contract["allowed_action_overrides"].get(reason, []))
                if action is _NOT_LITERAL:
                    failures.append(
                        f"{label}:{call.lineno}: action override must be a literal")
                elif action not in allowed:
                    failures.append(
                        f"{label}:{call.lineno}: invalid action override {action!r}")

    assert failures == []
