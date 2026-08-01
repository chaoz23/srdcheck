#!/usr/bin/env python3
"""Regenerate tool.json — the agent-facing capability card at the repo root.

tool.json is *generated*, never hand-edited: the 0.5.0 release shipped a card
that still said "pre-release" and advertised 7 of 22 MCP tools, so agents could
not discover most of the surface. Run after any change to the query surface:

    python3 scripts/gen_tool_json.py

tests/test_metadata_fresh.py fails if the committed file is stale.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck import __version__                      # noqa: E402
from srdcheck.access import default_adapter_paths     # noqa: E402
from srdcheck.engine import Engine                    # noqa: E402
from srdcheck.mcp import PROTOCOL_VERSION, build_tools  # noqa: E402


def build():
    engine = Engine(default_adapter_paths())
    tools, _ = build_tools(engine)
    rulesets = [{"name": a.manifest.get("name"),
                 "version": a.manifest.get("version")}
                for a in engine.adapters]
    subcommands = {
        "jurisdiction <name>": (
            "Is this spell/creature/condition/action known to the loaded "
            "rulesets? exit 0 = known content (categories in payload); "
            "exit 2 = unknown/third-party content."),
        "cite <heading>": (
            "Verbatim, page-numbered source text for a named SRD heading. "
            "Provenance surface: returns the page's own text, never "
            "interpretation."),
        "query <type> <params-json>": (
            "Adjudicate a structured proposal. Query types are supplied by "
            "the loaded adapters; see query_types below."),
        "--pipe": "Read one {\"type\", \"params\"} JSON query from stdin.",
        "--schema": "Print JSON Schema for input and output.",
        "capabilities": ("Print engine, protocol, adapter versions/digests, "
                         "query types, and MCP tool names."),
    }
    return {
        "name": "srdcheck",
        "version": __version__,
        "description": (
            "Deterministic rules verdicts over the SRD for game-running "
            "agents. Exit codes are the verdict: 0 legal, 1 illegal, "
            "2 cannot-adjudicate (unknown content or GM discretion — an "
            "honest refusal, not an error). Every verdict carries citations "
            "to the source text."),
        "status": "alpha; query surface may change within 0.x",
        "rulesets": rulesets,
        "invocation": {
            "command": "python -m srdcheck",
            "subcommands": subcommands,
            "query_types": sorted(
                qt for a in engine.adapters for qt in a.query_meta),
        },
        "output": ("JSON verdict object on stdout: {verdict, exit_code, why, "
                   "citations[], rule_ids[], adapter}"),
        "notes": (
            "The 'why' field is templated from cited rule text, not "
            "model-generated. Verdicts are deterministic: same query, same "
            "answer, every time. turn.options and turn.plan are "
            "consistency-tested against each other."),
        "mcp": {
            "command": "python3 -m srdcheck.mcp",
            "transport": "stdio",
            "protocolVersion": PROTOCOL_VERSION,
            "tools": [t["name"] for t in tools],
            "notes": (
                "Zero-dependency stdlib MCP server. Tool descriptions/schemas "
                "are supplied by loaded adapters (queries.json). Verdicts "
                "arrive as structuredContent; illegal is a result, not an "
                "error."),
        },
        "_generated_by": "scripts/gen_tool_json.py",
    }


def render():
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    (ROOT / "tool.json").write_text(render(), encoding="utf-8")
    n = len(build()["mcp"]["tools"])
    print(f"wrote tool.json — version {__version__}, {n} MCP tools")
