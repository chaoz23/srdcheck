"""Issue #33: facts, rules, DM decisions, and mutation never blur together."""

import json
import io
import sys

from srdcheck import load_adapter
from srdcheck import cli
from srdcheck.mcp import Server
from srdcheck.schema import validate
from srdcheck.verdict import VERDICT_OUTPUT_SCHEMA


def _metadata():
    return [{
        "path": "/spent_since_turn_start",
        "source": {"kind": "agent", "id": "discord-ai-dm"},
        "confidence": 0.93,
    }]


def _decision():
    return {
        "kind": "override",
        "outcome": "The reaction is unavailable due to a table effect.",
        "origin": {"kind": "dm", "id": "discord-ai-dm"},
        "scope": {"kind": "session", "id": "session-7"},
        "reason": "Temporary scene ruling.",
    }


def test_rule_facts_dm_decision_and_mutation_are_separate():
    result = load_adapter("srd-5.2.1").query(
        "reaction.available",
        {"spent_since_turn_start": False, "conditions": []},
        asserted_facts=_metadata(), table_decision=_decision())

    validate(result, VERDICT_OUTPUT_SCHEMA)
    assert result["verdict"] == "legal"
    assert result["rule_result"]["verdict"] == "legal"
    assert result["rule_result"]["authority"] == "rules-advisory"
    assert result["table_decision"]["outcome"].startswith(
        "The reaction is unavailable")
    assert result["state_mutation"] == {"status": "none", "operations": []}
    asserted = {fact["path"]: fact for fact in result["facts"]["asserted"]}
    assert asserted["/spent_since_turn_start"]["source"] == {
        "kind": "agent", "id": "discord-ai-dm"}
    assert asserted["/spent_since_turn_start"]["confidence"] == 0.93
    assert set(result["facts"]["consumed"]) == set(asserted)
    assert "DM override for session scope" in result["explanation"][
        "table_decision"]
    assert result["explanation"]["state_mutation"] == (
        "No state mutation was performed.")


def test_legacy_params_are_caller_assertions_with_unknown_confidence():
    result = load_adapter("srd-5.2.1").query(
        "reaction.available",
        {"spent_since_turn_start": False, "conditions": []})
    by_path = {fact["path"]: fact for fact in result["facts"]["asserted"]}
    assert by_path["/spent_since_turn_start"]["source"] == {"kind": "caller"}
    assert by_path["/spent_since_turn_start"]["confidence"] is None
    assert result["table_decision"] is None


def test_invalid_fact_path_is_asserted_never_consumed():
    result = load_adapter("srd-5.2.1").query(
        "reaction.available",
        {"spent_since_turn_start": False},
        asserted_facts=[{
            "path": "/heard_over_voice",
            "source": {"kind": "transcript", "id": "utterance-9"},
            "confidence": 0.51,
        }])
    assert result["exit_code"] == 2
    assert result["data"]["reason_code"] == "invalid-input"
    assert result["facts"]["consumed"] == []


def test_missing_and_derived_facts_are_not_assumptions():
    missing = load_adapter("srd-5.2.1").query(
        "mage-hand.use", {"kind": "manipulate_object", "distance_ft": 10})
    assert missing["data"]["reason_code"] == "missing-fact"
    assert missing["facts"]["missing"] == [{"path": "weight_lb"}]
    assert missing["assumptions"]

    derived = load_adapter("srd-5.2.1").query(
        "encounter.xp-budget",
        {"level": 1, "difficulty": "low", "party_size": 4})
    values = {fact["path"]: fact["value"]
              for fact in derived["facts"]["derived"]}
    assert values["/data/total"] == 200


def test_mcp_accepts_provenance_without_passing_it_to_adapter_schema():
    server = Server()
    server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    })
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = server.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "reaction_available",
            "arguments": {
                "spent_since_turn_start": False,
                "asserted_facts": _metadata(),
                "table_decision": _decision(),
            },
        },
    })
    assert response["result"]["isError"] is False
    result = response["result"]["structuredContent"]
    assert "/spent_since_turn_start" in result["facts"]["consumed"]
    assert result["facts"]["asserted"][0]["source"]["kind"] == "agent"
    assert result["table_decision"]["origin"]["kind"] == "dm"
    assert json.loads(response["result"]["content"][0]["text"]) == result


def test_cli_pipe_and_query_flags_accept_the_same_metadata(monkeypatch, capsys):
    params = {"spent_since_turn_start": False}
    envelope = {
        "type": "reaction.available", "params": params,
        "asserted_facts": _metadata(), "table_decision": _decision(),
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(envelope)))
    assert cli.main(["--pipe"]) == 0
    piped = json.loads(capsys.readouterr().out)

    assert cli.main([
        "query", "reaction.available", json.dumps(params),
        "--asserted-facts", json.dumps(_metadata()),
        "--table-decision", json.dumps(_decision()),
    ]) == 0
    direct = json.loads(capsys.readouterr().out)
    assert direct == piped


def test_event_next_state_is_a_proposal_not_an_applied_mutation():
    adapter = load_adapter("toy-tictactoe")
    result = adapter.query("ttt.move", {
        "board": ["", "", "", "", "", "", "", "", ""],
        "player": "X", "cell": 0,
    })
    assert result["state_mutation"]["status"] == "none"

    # The SRD reducer is the existing state-transition surface. Its next state
    # is explicit but remains a proposal owned by the caller.
    from srdcheck.access import default_adapter_paths
    from srdcheck.engine import Engine
    engine = Engine(default_adapter_paths())
    state = {
        "speed": 30, "conditions": [], "turn": {
            "action_spent": False, "bonus_action_spent": False,
            "reaction_spent": False, "free_interaction_spent": False,
            "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0,
        },
        "hp": 10, "hp_max": 10, "dead": False, "stable": False,
        "death_save_successes": 0, "death_save_failures": 0,
    }
    reduced = engine.query("event.apply", {
        "state": state, "event": {"type": "round-advance"},
    }).as_dict()
    assert reduced["state_mutation"]["status"] == "proposed"
    assert reduced["state_mutation"]["operations"][0]["path"] == "/"
    assert reduced["explanation"]["state_mutation"] == (
        "A replacement state was proposed but not persisted.")
