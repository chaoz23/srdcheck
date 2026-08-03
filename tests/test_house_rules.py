"""Issue #35: DM policy is portable, scoped, deterministic table state."""

import io
import json
import sys

import pytest

from srdcheck import cli, load_adapter
from srdcheck.house_rules import (MANIFEST_SCHEMA_ID, export_manifest,
                                  import_manifest, resolve_policy)
from srdcheck.mcp import Server
from srdcheck.schema import validate
from srdcheck.table_evaluation import project_table_evaluation
from srdcheck.verdict import VERDICT_OUTPUT_SCHEMA


def _policy(policy_id="no-reactions", scope="campaign", scope_id="camp-7",
            match=None, outcome="Reactions are unavailable at this table."):
    return {
        "id": policy_id,
        "author": {"kind": "dm", "id": "discord-ai-dm"},
        "reason": "Campaign uses a faster reaction variant.",
        "query": {"type": "reaction.available", "match": match or {}},
        "decision": {"kind": "override", "outcome": outcome},
        "scope": {"kind": scope, "id": scope_id},
        "visibility": "table",
        "reversible": True,
    }


def _manifest(*policies):
    return {"schema": MANIFEST_SCHEMA_ID, "table": "Friday game",
            "policies": list(policies) or [_policy()]}


def _params():
    return {"spent_since_turn_start": False, "conditions": []}


def test_matching_policy_applies_without_changing_source_rule_result():
    result = load_adapter("srd-5.2.1").query(
        "reaction.available", _params(), table_policy=_manifest(),
        policy_context={"campaign_id": "camp-7"})

    validate(result, VERDICT_OUTPUT_SCHEMA)
    assert result["rule_result"]["verdict"] == "legal"
    decision = result["table_decision"]
    assert decision["outcome"].startswith("Reactions are unavailable")
    assert decision["policy_id"] == "no-reactions"
    assert decision["origin"] == {"kind": "dm", "id": "discord-ai-dm"}
    assert decision["visibility"] == "table"
    assert decision["reversible"] is True
    assert decision["lineage"] == {
        "authority": "table-ruling",
        "affected_query": "reaction.available",
        "affected_rule_ids": result["rule_ids"],
        "source_rule_unchanged": True,
    }
    assert result["verdict"] == result["rule_result"]["verdict"]


@pytest.mark.parametrize("scope,context_key", [
    ("once", "request_id"),
    ("encounter", "encounter_id"),
    ("session", "session_id"),
    ("campaign", "campaign_id"),
])
def test_every_scope_binds_to_explicit_caller_context(scope, context_key):
    policy = _policy(scope=scope, scope_id="scope-1")
    assert resolve_policy(
        "reaction.available", _params(), _manifest(policy),
        {context_key: "scope-1"})["policy_id"] == "no-reactions"
    assert resolve_policy(
        "reaction.available", _params(), _manifest(policy),
        {context_key: "another-scope"}) is None


def test_more_specific_policy_wins_and_same_scope_conflict_fails_closed():
    campaign = _policy("campaign", "campaign", "camp-7",
                       outcome="Campaign ruling")
    encounter = _policy("encounter", "encounter", "enc-2",
                        outcome="Encounter ruling")
    context = {"campaign_id": "camp-7", "encounter_id": "enc-2"}
    decision = resolve_policy(
        "reaction.available", _params(), _manifest(campaign, encounter), context)
    assert decision["policy_id"] == "encounter"

    duplicate_scope = _policy("encounter-b", "encounter", "enc-2")
    result = load_adapter("srd-5.2.1").query(
        "reaction.available", _params(),
        table_policy=_manifest(encounter, duplicate_scope),
        policy_context=context)
    assert result["exit_code"] == 2
    assert result["data"]["reason_code"] == "invalid-input"
    assert "ambiguous matching table policies" in result["why"]


def test_query_match_uses_json_pointers_and_disabled_policy_does_not_apply():
    policy = _policy(match={"/spent_since_turn_start": False})
    assert resolve_policy(
        "reaction.available", _params(), _manifest(policy),
        {"campaign_id": "camp-7"}) is not None
    assert resolve_policy(
        "reaction.available", {"spent_since_turn_start": True},
        _manifest(policy), {"campaign_id": "camp-7"}) is None
    policy["enabled"] = False
    assert resolve_policy(
        "reaction.available", _params(), _manifest(policy),
        {"campaign_id": "camp-7"}) is None


def test_manifest_import_export_is_stable_human_readable_and_isolated():
    source = _manifest()
    rendered = export_manifest(source)
    imported = import_manifest(rendered)
    assert imported == source
    assert rendered.endswith("\n")
    assert json.loads(rendered) == source
    imported["policies"][0]["reason"] = "changed"
    assert source["policies"][0]["reason"] != "changed"


def test_duplicate_ids_and_bad_pointer_are_rejected():
    with pytest.raises(ValueError, match="duplicate table-policy"):
        import_manifest(_manifest(_policy(), _policy()))
    bad = _policy(match={"not-a-pointer": True})
    with pytest.raises(ValueError, match="invalid JSON Pointer"):
        import_manifest(_manifest(bad))


def test_array_pointer_does_not_accept_python_negative_indexing():
    policy = _policy(match={"/conditions/-1": "Prone"})
    assert resolve_policy(
        "reaction.available",
        {"spent_since_turn_start": False, "conditions": ["Prone"]},
        _manifest(policy), {"campaign_id": "camp-7"}) is None


def test_policy_is_not_attached_to_an_invalid_rules_request():
    result = load_adapter("srd-5.2.1").query(
        "reaction.available", {}, table_policy=_manifest(),
        policy_context={"campaign_id": "camp-7"})
    assert result["exit_code"] == 2
    assert result["table_decision"] is None


def test_cli_pipe_and_flags_apply_the_same_policy(monkeypatch, capsys):
    manifest = _manifest()
    context = {"campaign_id": "camp-7"}
    envelope = {"type": "reaction.available", "params": _params(),
                "table_policy": manifest, "policy_context": context}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(envelope)))
    assert cli.main(["--pipe"]) == 0
    piped = json.loads(capsys.readouterr().out)

    assert cli.main([
        "query", "reaction.available", json.dumps(_params()),
        "--table-policy", json.dumps(manifest),
        "--policy-context", json.dumps(context),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == piped


def test_cli_validates_and_exports_manifest_file(tmp_path, capsys):
    path = tmp_path / "table-policy.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    assert cli.main(["policy", "validate", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["policies"] == 1
    assert cli.main(["policy", "export", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == MANIFEST_SCHEMA_ID


def test_mcp_applies_policy_without_adding_a_policy_tool():
    server = Server()
    tool_names = {tool["name"] for tool in server.tools}
    assert "table_policy" not in tool_names
    server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}},
    })
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = server.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "reaction_available", "arguments": {
            **_params(), "table_policy": _manifest(),
            "policy_context": {"campaign_id": "camp-7"},
        }},
    })
    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]["table_decision"][
        "policy_id"] == "no-reactions"


def test_shared_table_evaluation_preserves_policy_as_advisory():
    verdict = load_adapter("srd-5.2.1").query(
        "reaction.available", _params(), table_policy=_manifest(),
        policy_context={"campaign_id": "camp-7"})
    projected = project_table_evaluation(
        verdict, "reaction.available", _params())
    assert projected["status"] == "checked_with_advisories"
    assert projected["exit_code"] == 0
    assert projected["advisories"][0]["authority"] == "table-ruling"
    assert projected["advisories"][0]["policy_id"] == "no-reactions"


def test_stored_dm_policy_resolves_authority_recovery_without_reprompting():
    policy = _policy(outcome="The hand can perform this flourish.")
    policy["query"] = {
        "type": "mage-hand.use", "match": {"/kind": "flourish"}}
    result = load_adapter("srd-5.2.1").query(
        "mage-hand.use", {"kind": "flourish"},
        table_policy=_manifest(policy),
        policy_context={"campaign_id": "camp-7"})
    assert result["rule_result"]["verdict"] == "cannot-adjudicate"
    assert result["data"]["reason_code"] == "gm-discretion"
    assert result["data"]["suggested_next_action"] == "apply-table-decision"
    assert result["table_decision"]["lineage"]["authority"] == "table-ruling"


def test_direct_decision_and_manifest_are_not_silently_combined():
    result = load_adapter("srd-5.2.1").query(
        "reaction.available", _params(), table_policy=_manifest(),
        policy_context={"campaign_id": "camp-7"},
        table_decision={
            "kind": "ruling", "outcome": "Direct ruling",
            "origin": {"kind": "dm"},
            "scope": {"kind": "once", "id": "request-1"},
        })
    assert result["exit_code"] == 2
    assert result["data"]["reason_code"] == "invalid-input"
    assert "cannot be combined" in result["why"]
