"""MCP server: protocol handshake, tool discovery, verdict calls — driven
through a real subprocess over stdio, the way a client would."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck import __version__  # noqa: E402
from srdcheck.mcp import PROTOCOL_VERSION, Server  # noqa: E402


def rpc(method, params=None, mid=1):
    m = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        m["params"] = params
    return m


def init_params(version=PROTOCOL_VERSION):
    return {
        "protocolVersion": version,
        "capabilities": {},
        "clientInfo": {"name": "srdcheck-tests", "version": "1.0"},
    }


def ready_server():
    server = Server()
    assert "result" in server.handle(rpc("initialize", init_params()))
    assert server.handle({"jsonrpc": "2.0",
                          "method": "notifications/initialized"}) is None
    return server


def test_handshake_and_tool_list():
    s = Server()
    init = s.handle(rpc("initialize", init_params()))
    assert init["result"]["serverInfo"]["name"] == "srdcheck"
    assert init["result"]["serverInfo"]["version"] == __version__
    assert s.handle({"jsonrpc": "2.0",
                     "method": "notifications/initialized"}) is None
    tools = s.handle(rpc("tools/list"))["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"jurisdiction", "table_evaluation",
                     "turn_plan", "turn_options",
                     "reaction_available", "roll_compose",
                     "attack_modifiers", "mage_hand_use", "spell_facts", "feature_uses",
                     "event_apply", "creature_valid", "creature_stats",
                     "encounter_xp_budget", "save_check", "check_make",
                     "concentration_check", "opportunity_attack_provoked", "grapple_initiate", "passive_perception", "help_assist",
                     "ttt_move", "ttt_options"}
    for t in tools:
        assert t["description"] and t["inputSchema"]["type"] == "object"
        if t["name"] == "table_evaluation":
            assert t["outputSchema"]["properties"]["schema_version"]["enum"] == [
                "table.evaluation/1.0"]
            assert t["outputSchema"]["properties"]["authority_status"]["enum"] == [
                "self_attested"]
        else:
            assert t["outputSchema"]["required"] == [
                "verdict", "exit_code", "why", "citations", "rule_ids", "adapter",
                "coverage_level", "checked_scope", "unchecked_scope", "assumptions",
                "facts", "rule_result", "table_decision", "state_mutation",
                "explanation"]


def test_tool_calls_return_verdicts():
    s = ready_server()
    r = s.handle(rpc("tools/call", {"name": "jurisdiction",
                                    "arguments": {"name": "Fireball"}}))
    sc = r["result"]["structuredContent"]
    assert sc["exit_code"] == 0 and not r["result"]["isError"]
    assert sc["data"]["categories"] == ["spell"]

    r = s.handle(rpc("tools/call", {"name": "jurisdiction",
                                    "arguments": {"name": "Fireball", "typo": True}}))
    sc = r["result"]["structuredContent"]
    assert sc["exit_code"] == 2
    assert sc["data"]["unknown_fields"] == ["typo"]

    r = s.handle(rpc("tools/call", {
        "name": "turn_plan",
        "arguments": {"speed": 30, "plan": [{"do": "bonus-action"},
                                            {"do": "bonus-action"}]}}))
    sc = r["result"]["structuredContent"]
    assert sc["exit_code"] == 1
    assert sc["citations"][0]["quote"]
    assert not r["result"]["isError"]  # an illegal verdict is not an error

    r = s.handle(rpc("tools/call", {"name": "nope", "arguments": {}}))
    assert r["result"]["isError"]


def test_table_evaluation_tool_is_opt_in_scoped_and_joinable():
    s = ready_server()
    response = s.handle(rpc("tools/call", {
        "name": "table_evaluation",
        "arguments": {
            "query_type": "mage-hand.use",
            "params": {"kind": "attack"},
            "context": {"session_id": "session-mcp",
                        "entity_refs": ["actor:wizard"],
                        "correlation_id": "discord-99"},
        },
    }))
    result = response["result"]["structuredContent"]
    assert response["result"]["isError"] is False
    assert result["status"] == "findings"
    assert result["authority_status"] == "self_attested"
    assert result["subject"]["session_id"] == "session-mcp"
    assert "srdcheck-query-scope:mage-hand.use" in \
        result["subject"]["entity_refs"]
    assert "correlation:discord-99" in result["subject"]["entity_refs"]
    finding = result["findings"][0]
    assert set(finding["evidence_refs"]) == set(
        finding["effective_policy"]["evidence"])

    r = s.handle(rpc("no/such/method"))
    assert r["error"]["code"] == -32601


def test_mcp_integer_arguments_match_canonical_handler_semantics():
    s = ready_server()

    def call(arguments, mid):
        response = s.handle(rpc("tools/call", {
            "name": "encounter_xp_budget", "arguments": arguments,
        }, mid=mid))
        assert not response["result"]["isError"]
        return response["result"]["structuredContent"]

    canonical = call({
        "level": 1, "difficulty": "low", "party_size": 4,
    }, 11)
    integral_float = call({
        "level": 1.0, "difficulty": "low", "party_size": 4.0,
    }, 12)

    assert integral_float == canonical
    assert integral_float["data"]["party_size"] == 4
    assert isinstance(integral_float["data"]["party_size"], int)


def test_protocol_negotiation_and_invalid_envelopes():
    s = Server()
    assert s.handle(rpc("tools/list"))["error"]["code"] == -32002
    assert "result" in s.handle(rpc("ping"))
    assert s.handle(rpc("initialize", {"protocolVersion": PROTOCOL_VERSION}))[
        "error"]["code"] == -32602
    init = s.handle(rpc("initialize", init_params("1900-01-01")))
    assert init["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert s.handle(rpc("notifications/initialized"))["error"]["code"] == -32600
    assert s.handle({"jsonrpc": "2.0",
                     "method": "notifications/initialized"}) is None
    assert s.handle(rpc("initialize", init_params()))["error"]["code"] == -32600
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/cancelled",
                     "params": {"requestId": 99}}) is None
    assert s.handle(rpc("notifications/cancelled", {"requestId": 99}))[
        "error"]["code"] == -32600
    assert s.handle({"jsonrpc": "2.0", "method": "tools/list"}) is None
    assert s.handle({"jsonrpc": "2.0", "method": "tools/call",
                     "params": {"name": "jurisdiction",
                                "arguments": {"name": "Fireball"}}}) is None
    assert s.handle([])["error"]["code"] == -32600
    assert s.handle({"jsonrpc": "1.0", "id": 1, "method": "ping"})["error"]["code"] == -32600
    assert s.handle({"jsonrpc": "2.0", "id": None, "method": "ping"})[
        "error"]["code"] == -32600
    assert s.handle({"jsonrpc": "2.0", "id": True, "method": "ping"})[
        "error"]["code"] == -32600
    assert s.handle(rpc("tools/call", [], mid=2))["error"]["code"] == -32602
    assert s.handle(rpc("tools/list", [], mid=4))["error"]["code"] == -32602
    assert s.handle(rpc("tools/call", {"name": "turn_plan", "arguments": []}, mid=3))["error"]["code"] == -32602


def test_stdio_returns_parse_error_for_bad_json():
    import io
    out = io.StringIO()
    Server().serve(io.StringIO("not-json\n"), out)
    response = json.loads(out.getvalue())
    assert response["id"] is None
    assert response["error"]["code"] == -32700


def test_internal_exception_is_sanitized():
    s = ready_server()
    s.engine.query = lambda *_: (_ for _ in ()).throw(RuntimeError("secret detail"))
    response = s.handle(rpc("tools/call", {
        "name": "turn_plan", "arguments": {"speed": 30, "plan": []}}))
    text = response["result"]["content"][0]["text"]
    assert response["result"]["isError"]
    assert "secret detail" not in text


def test_invalid_internal_output_is_sanitized():
    class BrokenVerdict:
        @staticmethod
        def as_dict():
            return {"exit_code": 0, "private": "must not escape"}

    s = ready_server()
    s.engine.query = lambda *_: BrokenVerdict()
    response = s.handle(rpc("tools/call", {
        "name": "turn_plan", "arguments": {"speed": 30, "plan": []}}))
    text = response["result"]["content"][0]["text"]
    assert response["result"]["isError"]
    assert text == "internal output validation failed"
    assert "private" not in text


def test_stdio_subprocess_end_to_end():
    proc = subprocess.Popen(
        [sys.executable, "-m", "srdcheck.mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT)
    msgs = [rpc("initialize", init_params(), mid=1),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("tools/list", mid=2),
            rpc("tools/call", {"name": "attack_modifiers",
                               "arguments": {"attacker": {"conditions": ["Invisible"]},
                                             "target": {"conditions": ["Prone"],
                                                        "can_see_attacker": False},
                                             "distance_ft": 20}}, mid=3)]
    out, _ = proc.communicate(
        "".join(json.dumps(m) + "\n" for m in msgs), timeout=30)
    replies = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert len(replies) == 3
    by_id = {r["id"]: r for r in replies}
    assert by_id[1]["result"]["serverInfo"]["name"] == "srdcheck"
    assert len(by_id[2]["result"]["tools"]) == 23
    sc = by_id[3]["result"]["structuredContent"]
    assert sc["data"]["roll"] == "straight"  # the infiltration composition
    assert proc.returncode == 0
