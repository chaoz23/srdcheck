"""T10 cold-start conformance: a stranger that knows NOTHING but the repo
checkout must reach a first correct verdict using only machine-readable
surfaces — tool.json, --schema, and the MCP handshake. No knowledge from
this test may come from anywhere except what those surfaces declare, so
this doubles as a doc-truth gate: if tool.json drifts from reality, this
fails."""

import json
import pathlib
import shlex
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_cmd(cmd, stdin=None):
    argv = shlex.split(cmd)
    if argv[0].startswith("python"):
        argv[0] = sys.executable
    return subprocess.run(argv, capture_output=True, text=True,
                          input=stdin, cwd=ROOT, timeout=60)


def test_cold_start_via_tool_json():
    t0 = time.perf_counter()
    tool = json.loads((ROOT / "tool.json").read_text())
    base = tool["invocation"]["command"]

    schema = json.loads(run_cmd(f"{base} --schema").stdout)
    assert set(schema["exit_codes"]) == {"0", "1", "2", "3"}

    sub = next(s for s in tool["invocation"]["subcommands"]
               if s.startswith("jurisdiction"))
    probe = sub.replace("<name>", shlex.quote("Anything At All"))
    r = run_cmd(f"{base} {probe}")
    verdict = json.loads(r.stdout)
    for field in schema["output"]["properties"]:
        assert field in verdict, field
    assert r.returncode == verdict["exit_code"]
    assert r.returncode in (0, 2)

    elapsed = time.perf_counter() - t0
    assert elapsed < 30, f"cold start took {elapsed:.1f}s"


def test_cold_start_via_mcp():
    tool = json.loads((ROOT / "tool.json").read_text())
    cmd = shlex.split(tool["mcp"]["command"])
    if cmd[0].startswith("python"):
        cmd[0] = sys.executable
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True, cwd=ROOT)
    first = "".join(json.dumps(m) + "\n" for m in msgs)
    proc.stdin.write(first)
    proc.stdin.flush()
    replies = [json.loads(proc.stdout.readline()) for _ in range(2)]
    tools = {t["name"]: t for t in replies[1]["result"]["tools"]}

    # A stranger picks the first tool whose required args it can synthesize
    # from the inputSchema alone: string -> "probe", integer -> 1.
    name, tdef = sorted(tools.items())[0]
    args = {}
    props = tdef["inputSchema"].get("properties", {})
    for req in tdef["inputSchema"].get("required", []):
        kind = props.get(req, {}).get("type", "string")
        args[req] = 1 if kind == "integer" else "probe"
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 3,
                                 "method": "tools/call",
                                 "params": {"name": name,
                                            "arguments": args}}) + "\n")
    proc.stdin.flush()
    reply = json.loads(proc.stdout.readline())
    proc.stdin.close()
    proc.wait(timeout=10)
    sc = reply["result"]["structuredContent"]
    assert sc["exit_code"] in (0, 1, 2)
    assert sc["why"]
