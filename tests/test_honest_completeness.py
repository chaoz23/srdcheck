"""Issue #31: omissions never masquerade as complete legality."""

import json
import pathlib

from srdcheck import load_adapter, project_table_evaluation
from srdcheck.cli import main
from srdcheck.mcp import PROTOCOL_VERSION, Server


ROOT = pathlib.Path(__file__).resolve().parent.parent
ADAPTER = load_adapter("srd-5.2.1")


def _missing(result):
    assert result["exit_code"] == 2
    assert result["data"]["reason_code"] == "missing-fact"
    assert result["data"]["suggested_next_action"] == "provide-facts"
    return result["data"]["missing_inputs"]


def _rpc(method, params=None, mid=1):
    request = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        request["params"] = params
    return request


def _ready_server():
    server = Server()
    response = server.handle(_rpc("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "completeness-test", "version": "1.0"},
    }))
    assert "result" in response
    assert server.handle({"jsonrpc": "2.0",
                          "method": "notifications/initialized"}) is None
    return server


def test_python_requires_only_facts_that_can_change_mage_hand_result():
    assert _missing(ADAPTER.query(
        "mage-hand.use", {"kind": "manipulate_object"})) == [
            "distance_ft", "weight_lb"]
    assert _missing(ADAPTER.query(
        "mage-hand.use", {"kind": "open_unlocked"})) == ["distance_ft"]

    open_door = ADAPTER.query(
        "mage-hand.use", {"kind": "open_unlocked", "distance_ft": 20})
    assert open_door["exit_code"] == 0
    assert open_door["coverage_level"] == "rule-surface-complete"
    assert open_door["checked_scope"]
    assert open_door["unchecked_scope"]
    assert open_door["assumptions"]
    assert "legal only within this checked scope" in open_door["why"].lower()

    # A known prohibition or exceeded limit is decisive. Repair loops must not
    # ask for facts that cannot change the result.
    for proposal, rule_id in (
        ({"kind": "attack"}, "mage-hand.cant-attack"),
        ({"kind": "activate_magic_item"},
         "mage-hand.cant-activate-magic-items"),
        ({"kind": "manipulate_object", "distance_ft": 35},
         "mage-hand.range-leash"),
        ({"kind": "manipulate_object", "weight_lb": 11},
         "mage-hand.carry-limit"),
    ):
        result = ADAPTER.query("mage-hand.use", proposal)
        assert result["exit_code"] == 1
        assert rule_id in result["rule_ids"]
        assert result.get("data", {}).get("missing_inputs") is None

    discretionary = ADAPTER.query(
        "mage-hand.use", {"kind": "untie_knots"})
    assert discretionary["exit_code"] == 2
    assert discretionary["data"]["reason_code"] == "gm-discretion"
    assert discretionary["data"]["required_authority"] == "dm"
    assert discretionary["data"]["missing_inputs"] == []


def test_python_move_step_requires_explicit_feet():
    missing = ADAPTER.query(
        "turn.plan", {"speed": 30, "plan": [{"do": "move"}]})
    assert _missing(missing) == ["plan[0].feet"]
    assert missing["coverage_level"] == "budget-only"

    explicit_zero = ADAPTER.query(
        "turn.plan", {"speed": 30, "plan": [{"do": "move", "feet": 0}]})
    assert explicit_zero["exit_code"] == 0
    assert "legal only within this checked scope" in explicit_zero["why"].lower()


def test_native_cli_exposes_missing_facts_and_scope(capsys):
    params = json.dumps({"kind": "manipulate_object"})
    assert main(["query", "mage-hand.use", params]) == 2
    result = json.loads(capsys.readouterr().out)
    assert _missing(result) == ["distance_ft", "weight_lb"]
    assert result["coverage_level"] == "rule-surface-complete"
    assert result["checked_scope"]
    assert result["unchecked_scope"]
    assert result["assumptions"]


def test_mcp_exposes_conditional_repair_and_decisive_prohibition():
    server = _ready_server()

    missing_response = server.handle(_rpc("tools/call", {
        "name": "mage_hand_use",
        "arguments": {"kind": "manipulate_object"},
    }, mid=2))
    missing = missing_response["result"]["structuredContent"]
    assert _missing(missing) == ["distance_ft", "weight_lb"]
    assert missing["coverage_level"] == "rule-surface-complete"

    attack_response = server.handle(_rpc("tools/call", {
        "name": "mage_hand_use", "arguments": {"kind": "attack"},
    }, mid=3))
    attack = attack_response["result"]["structuredContent"]
    assert attack["exit_code"] == 1
    assert attack["rule_ids"] == ["mage-hand.cant-attack"]
    assert attack_response["result"]["isError"] is False

    move_response = server.handle(_rpc("tools/call", {
        "name": "turn_plan",
        "arguments": {"speed": 30, "plan": [{"do": "move"}]},
    }, mid=4))
    assert _missing(move_response["result"]["structuredContent"]) == [
        "plan[0].feet"]


def test_table_evaluation_maps_missing_facts_without_false_clean():
    params = {"kind": "manipulate_object"}
    result = project_table_evaluation(
        ADAPTER.query("mage-hand.use", params), "mage-hand.use", params)
    assert result["status"] == "incomplete"
    assert result["exit_code"] == 2
    assert result["coverage"]["complete"] is False
    assert result["errors"][0]["code"] == "srdcheck.missing_fact"
    assert result["errors"][0]["pointer"] == "distance_ft"

    attack_params = {"kind": "attack"}
    decisive = project_table_evaluation(
        ADAPTER.query("mage-hand.use", attack_params),
        "mage-hand.use", attack_params)
    assert decisive["status"] == "findings"
    assert decisive["exit_code"] == 1
    assert decisive["coverage"]["complete"] is True


def test_every_first_party_golden_has_concrete_scope_and_scoped_legal_copy():
    for path in sorted((ROOT / "tests/golden").rglob("*.json")):
        result = json.loads(path.read_text())
        assert result["coverage_level"] != "unknown", path
        assert result["checked_scope"], path
        assert result["unchecked_scope"], path
        assert result["assumptions"], path
        if result["exit_code"] == 0:
            assert "legal only within this checked scope" in result[
                "why"].lower(), path
