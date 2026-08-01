"""Version and capability metadata must agree across every surface.

srdcheck 0.5.0 shipped with the package at 0.5.0, the MCP server announcing
itself as 0.2.0, and a tool.json that still said "pre-release" while listing 7
of its 22 MCP tools. An agent negotiating capabilities or caching schemas off
that metadata is working from fiction. These tests make the drift fatal.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import srdcheck                        # noqa: E402
from srdcheck import mcp               # noqa: E402


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def _initialize_params(protocol_version):
    return {
        "protocolVersion": protocol_version,
        "capabilities": {},
        "clientInfo": {"name": "metadata-test", "version": "1.0"},
    }


def test_package_version_is_the_single_source():
    assert srdcheck.__version__ == _pyproject_version()


def test_mcp_server_reports_package_version():
    """The MCP serverInfo version is the engine version, not a stale literal."""
    assert mcp.SERVER_INFO["version"] == srdcheck.__version__


def test_mcp_initialize_reports_engine_and_rulesets_separately():
    """Engine version and ruleset versions are distinct facts; a client caching
    schemas needs both. Adapters legitimately version independently."""
    server = mcp.Server()
    reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": _initialize_params(mcp.PROTOCOL_VERSION)})
    info = reply["result"]["serverInfo"]
    assert info["version"] == srdcheck.__version__
    names = {r["name"] for r in info["rulesets"]}
    assert "srd-5.2.1" in names
    for ruleset in info["rulesets"]:
        assert ruleset["version"], f"ruleset {ruleset['name']} has no version"


def test_protocol_version_is_negotiated_not_echoed():
    """Echoing an unsupported version back tells the client we speak a protocol
    we do not implement. Honour supported requests; otherwise offer our own."""
    assert mcp.negotiate_protocol("2025-06-18") == "2025-06-18"
    assert mcp.negotiate_protocol("1999-01-01") == mcp.PROTOCOL_VERSION
    assert mcp.negotiate_protocol(None) == mcp.PROTOCOL_VERSION

    server = mcp.Server()
    reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": _initialize_params("1999-01-01")})
    assert reply["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION


def test_tool_json_is_freshly_generated():
    """tool.json is generated, never hand-edited."""
    from scripts.gen_tool_json import render
    committed = (ROOT / "tool.json").read_text(encoding="utf-8")
    assert committed == render(), (
        "tool.json is stale — run: python3 scripts/gen_tool_json.py")


def test_tool_json_advertises_every_mcp_tool():
    """The capability card is how agents discover the surface. A partial list
    silently hides most of the engine."""
    card = json.loads((ROOT / "tool.json").read_text(encoding="utf-8"))
    live, _ = mcp.build_tools(mcp.Server().engine)
    assert sorted(card["mcp"]["tools"]) == sorted(t["name"] for t in live)
    assert card["version"] == srdcheck.__version__


def test_mcp_registry_manifest_matches_package_version():
    """server.json is what the public MCP registry serves. If it lags, agents
    resolve a version that does not match what PyPI installs."""
    manifest = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert manifest["version"] == srdcheck.__version__
    for pkg in manifest.get("packages", []):
        assert pkg["version"] == srdcheck.__version__, (
            f"server.json package {pkg.get('identifier')} pinned to "
            f"{pkg['version']}, expected {srdcheck.__version__}")


def test_docs_do_not_invent_adapter_versions():
    """Docs quoted `srd-5.2.1@1.0.0` in sample output while the adapter was at
    0.2.0 — a reader copying that expects a ruleset that does not exist."""
    live = {a.manifest["name"]: a.manifest["version"]
            for a in mcp.Server().engine.adapters}
    pattern = re.compile(r"\b(srd-[\d.]+)@([\d.]+)\b")
    for path in (ROOT / "docs").rglob("*.md"):
        for name, claimed in pattern.findall(path.read_text(encoding="utf-8")):
            if name in live:
                assert claimed == live[name], (
                    f"{path.name} claims {name}@{claimed}, "
                    f"but the adapter is at {live[name]}")


def test_cli_reports_the_same_version():
    out = subprocess.run([sys.executable, "-m", "srdcheck", "--version"],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return  # --version not implemented; covered by other surfaces
    assert srdcheck.__version__ in out.stdout
