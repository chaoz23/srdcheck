"""Minimal MCP stdio server. Zero dependencies.

Run: python -m srdcheck.mcp

Exposes one tool per query type declared by the loaded adapters (their
queries.json supplies names, descriptions, and input schemas — this module
stays content-neutral, T7), plus the kernel-level jurisdiction lookup.
Transport: newline-delimited JSON-RPC 2.0 on stdio; protocol pinned below.
"""

import json
import sys

from . import __version__
from .engine import Engine

PROTOCOL_VERSION = "2025-06-18"
# Protocol revisions this server can actually speak, newest first. Used to
# negotiate: we must not echo a client's requested version back unless we
# support it, or the client will assume features we do not implement.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26")
# Engine version comes from the package, never a second hardcoded literal.
# Adapter (ruleset) versions are reported separately — see _server_info.
SERVER_INFO = {"name": "srdcheck", "version": __version__}


def negotiate_protocol(requested):
    """Return the protocol revision to run at, per MCP initialize semantics:
    honour the client's request when we support it, else offer our newest."""
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return PROTOCOL_VERSION

JURISDICTION_TOOL = {
    "name": "jurisdiction",
    "description": ("Look up whether a named entity exists in the loaded "
                    "rulesets' content registries. exit_code 0 = known "
                    "content (categories in payload); 2 = unknown or "
                    "third-party content, honestly refused."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
}


def build_tools(engine):
    tools = [JURISDICTION_TOOL]
    mapping = {"jurisdiction": "jurisdiction"}
    for a in engine.adapters:
        for qt, meta in sorted(a.query_meta.items()):
            name = qt.replace(".", "_").replace("-", "_")
            tools.append({"name": name,
                          "description": meta.get("description", ""),
                          "inputSchema": meta.get("inputSchema",
                                                  {"type": "object"})})
            mapping[name] = qt
    return tools, mapping


class Server:
    def __init__(self, adapter_paths=None):
        from .access import default_adapter_paths
        self.engine = Engine(adapter_paths or default_adapter_paths())
        self.tools, self.mapping = build_tools(self.engine)

    def _server_info(self):
        """Engine version and ruleset versions are distinct facts: the engine
        is this package, the rulesets are whatever adapters are loaded. A
        client caching schemas needs both, so report them separately."""
        info = dict(SERVER_INFO)
        info["rulesets"] = [
            {"name": a.manifest.get("name"), "version": a.manifest.get("version")}
            for a in self.engine.adapters
        ]
        return info

    def handle(self, msg):
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            return self._result(mid, {
                "protocolVersion": negotiate_protocol(
                    msg.get("params", {}).get("protocolVersion")),
                "capabilities": {"tools": {}},
                "serverInfo": self._server_info()})
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return self._result(mid, {})
        if method == "tools/list":
            return self._result(mid, {"tools": self.tools})
        if method == "tools/call":
            return self._call(mid, msg.get("params", {}))
        if mid is not None:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601,
                              "message": f"method not found: {method}"}}
        return None

    def _call(self, mid, params):
        name = params.get("name")
        if name not in self.mapping:
            return self._result(mid, {
                "content": [{"type": "text",
                             "text": f"unknown tool: {name}"}],
                "isError": True})
        args = params.get("arguments") or {}
        qt = self.mapping[name]
        try:
            if qt == "jurisdiction":
                vd = self.engine.jurisdiction(args.get("name", "")).as_dict()
            else:
                vd = self.engine.query(qt, args).as_dict()
        except Exception as e:  # noqa: BLE001 — protocol error, not a verdict
            return self._result(mid, {
                "content": [{"type": "text", "text": f"error: {e}"}],
                "isError": True})
        return self._result(mid, {
            "content": [{"type": "text", "text": json.dumps(vd, indent=1)}],
            "structuredContent": vd,
            "isError": False})

    @staticmethod
    def _result(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def serve(self, stdin=None, stdout=None):
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle(msg)
            if resp is not None:
                stdout.write(json.dumps(resp) + "\n")
                stdout.flush()


def script():
    Server().serve()


if __name__ == "__main__":
    script()
