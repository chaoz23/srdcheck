"""Integrity and scoring tests for the preregistered issue #32 study."""

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "bench" / "tool_selection" / "harness.py"
SPEC = importlib.util.spec_from_file_location("tool_selection_harness", PATH)
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def test_preregistered_case_set_matches_the_engine():
    cases = HARNESS.load_cases()
    assert len(cases) == 28
    assert sum(case["lane"] == "common" for case in cases) == 24
    assert sum(case["lane"] == "protocol-only" for case in cases) == 4
    assert HARNESS.validate_cases(HARNESS.CASES_PATH) == []
    assert len(HARNESS.case_digest()) == 64


def test_arms_are_frozen_and_compact_budget_is_explicit():
    _, specialized = HARNESS.catalog("specialized")
    _, compact = HARNESS.catalog("compact")
    assert len(specialized) == 23
    assert [tool["name"] for tool in compact] == [
        "capabilities", "evaluate", "enumerate", "explain"]
    assert len(compact) <= 6
    assert len(HARNESS.render_prompt(HARNESS.load_cases()[0], "compact", compact)) \
        < len(HARNESS.render_prompt(HARNESS.load_cases()[0], "specialized",
                                    specialized))


def test_perfect_common_calls_execute_in_both_arms():
    engine, _ = HARNESS.catalog("specialized")
    case = HARNESS.load_cases()[0]
    for arm in ("specialized", "compact"):
        answer = HARNESS.expected_call(case, arm)
        result = HARNESS.assess(engine, case, arm, json.dumps(answer))
        assert result["selection_success"]
        assert result["argument_success"]
        assert result["execution_success"]
        assert result["first_call_success"]
        assert not result["broken"]


def test_protocol_only_lane_does_not_inflate_head_to_head_result():
    engine, _ = HARNESS.catalog("specialized")
    case = next(case for case in HARNESS.load_cases()
                if case["operation"] == "explain")
    specialized = HARNESS.expected_call(case, "specialized")
    compact = HARNESS.expected_call(case, "compact")
    assert specialized == {"tool": None, "arguments": {}}
    assert compact["tool"] == "explain"
    assert HARNESS.assess(engine, case, "specialized",
                          '{"tool":null,"arguments":{}}')["first_call_success"]
    assert HARNESS.assess(engine, case, "compact",
                          json.dumps(compact))["first_call_success"]


def test_dropped_fact_and_broken_output_fail_first_call():
    engine, _ = HARNESS.catalog("specialized")
    case = HARNESS.load_cases()[0]
    dropped = '{"tool":"turn_plan","arguments":{"speed":30,"plan":[]}}'
    result = HARNESS.assess(engine, case, "specialized", dropped)
    assert result["selection_success"]
    assert not result["argument_success"]
    assert not result["first_call_success"]
    assert HARNESS.assess(engine, case, "specialized", "I would use turn_plan")[
        "broken"]
