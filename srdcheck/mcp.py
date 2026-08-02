"""Minimal MCP stdio server. Zero dependencies.

Run: python -m srdcheck.mcp

Exposes one tool per query type declared by the loaded adapters (their
queries.json supplies names, descriptions, and input schemas — this module
stays content-neutral, T7), plus the kernel-level jurisdiction lookup.
Transport: newline-delimited JSON-RPC 2.0 on stdio; protocol pinned below.
"""

import json
import sys
from copy import deepcopy

from . import __version__
from .engine import Engine, NON_EMPTY_NAME_INPUT_SCHEMA
from .schema import ValidationError, validate
from .table_evaluation import (
    CALLER_CONTEXT_SCHEMA, TABLE_EVALUATION_OUTPUT_SCHEMA,
    project_table_evaluation,
)
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
                    "rulesets' content registries. exit_code 0 = known "
                    "content (all matching categories in data.categories); "
                    "2 = unknown or "
                    "third-party content, honestly refused."),
    "inputSchema": NON_EMPTY_NAME_INPUT_SCHEMA,
    "outputSchema": VERDICT_OUTPUT_SCHEMA,
}

TABLE_EVALUATION_TOOL = {
    "name": "table_evaluation",
    "description": (
        "Adjudicate one named SRDCheck query and project its exact scoped "
        "result into deterministic table.evaluation/1.0. Always self-attested, "
        "including when the calling agent is the DM; table authority remains "
        "with the caller or protected host."),
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query_type", "params"],
        "properties": {
            "query_type": {"type": "string", "minLength": 1},
            "params": {"type": "object"},
            "context": CALLER_CONTEXT_SCHEMA,
        },
    },
    "outputSchema": TABLE_EVALUATION_OUTPUT_SCHEMA,
}


def _published_input_schema(adapter, meta):
    """Expand adapter-local refs into self-contained MCP tool schemas.

    Engine dispatch keeps the shallow request schema so the reducer can label
    a malformed existing state ``invalid-input`` instead of mistaking a
    structural omission for a missing event fact. MCP discovery still exposes
    the complete canonical state shape for client-side validation.
    """
    schema = deepcopy(meta.get("inputSchema", {"type": "object"}))
    for property_name, reference in meta.get(
            "inputSchemaPropertyRefs", {}).items():
        filename, marker, pointer = reference.partition("#/")
        if not marker or not filename or not pointer:
            raise ValueError(f"invalid adapter-local schema ref: {reference!r}")
        source = (adapter.root / filename).resolve()
        root = adapter.root.resolve()
        if source != root and root not in source.parents:
            raise ValueError(f"schema ref escapes adapter root: {reference!r}")
        value = json.loads(source.read_text(encoding="utf-8"))
        for token in pointer.split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            value = value[token]
        schema.setdefault("properties", {})[property_name] = deepcopy(value)
    return schema


def build_tools(engine):
    tools = [JURISDICTION_TOOL, TABLE_EVALUATION_TOOL]
    mapping = {"jurisdiction": "jurisdiction",
               "table_evaluation": "table_evaluation"}
    for a in engine.adapters:
        for qt, meta in sorted(a.query_meta.items()):
            name = qt.replace(".", "_").replace("-", "_")
            tools.append({"name": name,
                          "description": meta.get("description", ""),
                          "inputSchema": _published_input_schema(a, meta),
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
        if qt == "table_evaluation":
            try:
                normalized = validate(
                    args, TABLE_EVALUATION_TOOL["inputSchema"])
            except ValidationError:
                return self._result(mid, {
                    "content": [{"type": "text",
                                 "text": "invalid table_evaluation arguments"}],
                    "isError": True,
                })
        try:
            if qt == "table_evaluation":
                query_type = normalized["query_type"]
                query_params = normalized["params"]
                native = self.engine.query(query_type, query_params).as_dict()
                validate(native, VERDICT_OUTPUT_SCHEMA)
                vd = project_table_evaluation(
                    native, query_type, query_params, normalized.get("context"))
                validate(vd, TABLE_EVALUATION_OUTPUT_SCHEMA)
            elif qt == "jurisdiction":
                vd = self.engine.query("jurisdiction", args).as_dict()
                validate(vd, VERDICT_OUTPUT_SCHEMA)
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
            except (ValueError, RecursionError):
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
