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
from .engine import Engine, JURISDICTION_INPUT_SCHEMA
from .schema import ValidationError, validate
from .verdict import VERDICT_OUTPUT_SCHEMA

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
                    "rulesets' content registries. exit_code 0 = registered "
                    "content; 2 = unknown or "
                    "third-party content, honestly refused."),
    "inputSchema": JURISDICTION_INPUT_SCHEMA,
    "outputSchema": VERDICT_OUTPUT_SCHEMA,
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
                                                  {"type": "object"}),
                          "outputSchema": VERDICT_OUTPUT_SCHEMA})
            mapping[name] = qt
    return tools, mapping


class Server:
    def __init__(self, adapter_paths=None):
        from .access import default_adapter_paths
        self.engine = Engine(adapter_paths or default_adapter_paths())
        self.tools, self.mapping = build_tools(self.engine)
        self.lifecycle = "new"

    def _server_info(self):
        """Engine version and ruleset versions are distinct facts: the engine
        is this package, the rulesets are whatever adapters are loaded. A
        client caching schemas needs both, so report them separately."""
        info = dict(SERVER_INFO)
        info["rulesets"] = [
            {"name": a.manifest.get("name"),
             "version": a.manifest.get("version"),
             "data_version": a.data_version,
             "rules_version": a.rules_version}
            for a in self.engine.adapters
        ]
        return info

    def handle(self, msg):
        if not isinstance(msg, dict):
            return self._error(None, -32600, "invalid request")
        is_notification = "id" not in msg
        mid = msg.get("id")
        if not is_notification and (isinstance(mid, bool) or
                                    not isinstance(mid, (str, int))):
            return self._error(None, -32600, "invalid request")
        if msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            return self._error(mid, -32600, "invalid request")
        method = msg.get("method")
        if method == "initialize":
            if is_notification:
                return None
            if self.lifecycle != "new":
                return self._error(mid, -32600, "server is already initialized")
            params = msg.get("params")
            client_info = params.get("clientInfo") if isinstance(params, dict) else None
            if (not isinstance(params, dict)
                    or not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(client_info, dict)
                    or not isinstance(client_info.get("name"), str)
                    or not isinstance(client_info.get("version"), str)):
                return self._error(mid, -32602, "invalid params")
            self.lifecycle = "initializing"
            return self._result(mid, {
                "protocolVersion": negotiate_protocol(
                    msg.get("params", {}).get("protocolVersion")),
                "capabilities": {"tools": {}},
                "serverInfo": self._server_info()})
        if method == "notifications/initialized":
            if not is_notification:
                return self._error(mid, -32600,
                                   "notifications/initialized must be a notification")
            if self.lifecycle == "initializing":
                self.lifecycle = "ready"
            return None
        if method == "notifications/cancelled":
            if not is_notification:
                return self._error(mid, -32600,
                                   "notifications/cancelled must be a notification")
            return None
        if method == "ping":
            if is_notification:
                return None
            return self._result(mid, {})
        if self.lifecycle != "ready":
            if is_notification:
                return None
            return self._error(mid, -32002, "server not initialized")
        if is_notification:
            return None
        if method == "tools/list":
            if not isinstance(msg.get("params", {}), dict):
                return self._error(mid, -32602, "invalid params")
            return self._result(mid, {"tools": self.tools})
        if method == "tools/call":
            params = msg.get("params", {})
            if not isinstance(params, dict):
                return self._error(mid, -32602, "invalid params")
            return self._call(mid, params)
        if not is_notification:
            return self._error(mid, -32601, f"method not found: {method}")
        return None

    def _call(self, mid, params):
        name = params.get("name")
        if not isinstance(name, str):
            return self._error(mid, -32602, "invalid params: tool name is required")
        if name not in self.mapping:
            return self._result(mid, {
                "content": [{"type": "text",
                             "text": f"unknown tool: {name}"}],
                "isError": True})
        args = params.get("arguments", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return self._error(mid, -32602, "invalid params: arguments must be an object")
        qt = self.mapping[name]
        try:
            if qt == "jurisdiction":
                vd = self.engine.query("jurisdiction", args).as_dict()
            else:
                vd = self.engine.query(qt, args).as_dict()
            validate(vd, VERDICT_OUTPUT_SCHEMA)
        except ValidationError:
            return self._result(mid, {
                "content": [{"type": "text", "text": "internal output validation failed"}],
                "isError": True})
        except Exception:  # noqa: BLE001 — protocol error, not a verdict
            return self._result(mid, {
                "content": [{"type": "text", "text": "internal tool execution failed"}],
                "isError": True})
        return self._result(mid, {
            "content": [{"type": "text", "text": json.dumps(vd, indent=1)}],
            "structuredContent": vd,
            "isError": False})

    @staticmethod
    def _result(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _error(mid, code, message):
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": code, "message": message}}

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
                resp = self._error(None, -32700, "parse error")
                stdout.write(json.dumps(resp) + "\n")
                stdout.flush()
                continue
            resp = self.handle(msg)
            if resp is not None:
                stdout.write(json.dumps(resp) + "\n")
                stdout.flush()


def script():
    Server().serve()


if __name__ == "__main__":
    script()
