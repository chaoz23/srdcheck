"""MCP server: protocol handshake, tool discovery, verdict calls — driven
through a real subprocess over stdio, the way a client would."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.mcp import Server  # noqa: E402


def rpc(method, params=None, mid=1):
    m = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        m["params"] = params
    return m


def test_handshake_and_tool_list():
    s = Server()
    init = s.handle(rpc("initialize", {"protocolVersion": "2025-06-18"}))
    assert init["result"]["serverInfo"]["name"] == "srdcheck"
    assert s.handle({"jsonrpc": "2.0",
                     "method": "notifications/initialized"}) is None
    tools = s.handle(rpc("tools/list"))["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"jurisdiction", "turn_plan", "turn_options",
                     "reaction_available", "roll_compose",
                     "attack_modifiers", "mage_hand_use",
                     "event_apply", "creature_valid", "creature_stats",
                     "encounter_xp_budget", "save_check", "check_make",
                     "concentration_check", "ttt_move", "ttt_options"}
    for t in tools:
        assert t["description"] and t["inputSchema"]["type"] == "object"


def test_tool_calls_return_verdicts():
    s = Server()
    r = s.handle(rpc("tools/call", {"name": "jurisdiction",
                                    "arguments": {"name": "Fireball"}}))
    sc = r["result"]["structuredContent"]
    assert sc["exit_code"] == 0 and not r["result"]["isError"]

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

    r = s.handle(rpc("no/such/method"))
    assert r["error"]["code"] == -32601


def test_stdio_subprocess_end_to_end():
    proc = subprocess.Popen(
        [sys.executable, "-m", "srdcheck.mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT)
    msgs = [rpc("initialize", {"protocolVersion": "2025-06-18"}, mid=1),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("tools/list", mid=2),
            rpc("tools/call", {"name": "attack_modifiers",
                               "arguments": {"attacker": {"conditions": ["Invisible"]},
                                             "target": {"conditions": ["Prone"]},
                                             "distance_ft": 20}}, mid=3)]
    out, _ = proc.communicate(
        "".join(json.dumps(m) + "\n" for m in msgs), timeout=30)
    replies = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert len(replies) == 3
    by_id = {r["id"]: r for r in replies}
    assert by_id[1]["result"]["serverInfo"]["name"] == "srdcheck"
    assert len(by_id[2]["result"]["tools"]) == 16
    sc = by_id[3]["result"]["structuredContent"]
    assert sc["data"]["roll"] == "straight"  # the infiltration composition
    assert proc.returncode == 0
