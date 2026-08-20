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
                 "version": a.manifest.get("version"),
                 "data_version": a.data_version,
                 "rules_version": a.rules_version}
                for a in engine.adapters]
    subcommands = {
        "jurisdiction <name>": (
            "Is this named entity known to the loaded rulesets? exit 0 = "
            "known content (all matching categories in data.categories); "
            "exit 2 = unknown/third-party content."),
        "cite <heading>": (
            "Verbatim, page-numbered source text for a named SRD heading. "
            "Provenance surface: returns the page's own text, never "
            "interpretation."),
        "query <type> <params-json>": (
            "Adjudicate a structured proposal. Query types are supplied by "
            "the loaded adapters; see query_types below. Existing query tools "
            "accept optional table_policy and policy_context metadata."),
        "query <type> <params-json> --table-evaluation": (
            "Project the scoped verdict into deterministic, self-attested "
            "table.evaluation/1.0. Add --table-context JSON for caller-owned "
            "session/entity/correlation references. Table and execution "
            "authority stay external."),
        "--pipe": "Read one {\"type\", \"params\"} JSON query from stdin.",
        "--schema": "Print JSON Schema for input and output.",
        "capabilities": ("Print engine, protocol, adapter versions/digests, "
                         "query types, refusal recovery and observability "
                         "contracts, and MCP tool names."),
        "query ... --trace [--request-id <id>]": (
            "Keep the verdict on stdout and emit metadata-only lifecycle "
            "NDJSON on stderr."),
        "policy validate|export <manifest>": (
            "Import and validate a portable srdcheck.table-policy/1.0 JSON "
            "manifest, or export its canonical human/machine form."),
    }
    return {
        "name": "srdcheck",
        # FAMILY.md v2 clause 7 binds agent-first surfaces per member class.
        # Declared here so the conformance gate reads it from the artifact
        # rather than parsing the contract's prose.
        "family_class": "verdict",
        "version": __version__,
        "description": (
            "Deterministic rules verdicts over the SRD for game-running "
            "agents. Exit codes are scoped results: 0 passes the named "
            "checked scope, 1 conflicts with it, "
            "2 cannot-adjudicate (unknown content or a DM-authority decision, "
            "including when the caller is the agent-DM — an "
            "honest refusal, not an error). Applied rules carry citations; "
            "boundary refusals do not invent them."),
        "status": ("alpha; versioned machine schemas and the N/N-1 semantic "
                   "window are reported by `capabilities`"),
        "rulesets": rulesets,
        "invocation": {
            "command": "python -m srdcheck",
            "subcommands": subcommands,
            "query_types": sorted(
                qt for a in engine.adapters for qt in a.query_meta),
        },
        "output": ("JSON verdict object on stdout: {verdict, exit_code, why, "
                   "citations[], rule_ids[], adapter, data?}. Exit-2 data "
                   "contains stable reason and recovery fields. Schema and "
                   "refusal contract identities are published by --schema, "
                   "MCP outputSchema, and capabilities."),
        "table_evaluation": (
            "query/--pipe --table-evaluation maps legal to checked_clean "
            "(or checked_with_advisories when a table policy applies), "
            "illegal to an exact-evidence finding, and structured refusals to "
            "invalid, unsupported, or incomplete. Output is always "
            "self_attested. Its named-query scope is machine-readable and "
            "every finding evidence ref resolves in its effective policy. "
            "Stateful queries expose cursor.state_precondition_hash."),
        "notes": (
            "The 'why' field is templated explanatory prose, not a machine "
            "compatibility field. Verdicts are deterministic: same query, same "
            "answer, every time. On cannot-adjudicate, branch on structured "
            "recovery data rather than prose; an authorized agent-DM may "
            "resolve a DM-authority table ruling directly and reuse it through "
            "a caller-owned table-policy manifest. turn.options and "
            "turn.plan are consistency-tested against each other. For state "
            "writes, evaluate with event.apply and verify the exact proposal "
            "with transition.commit; the host owns atomic persistence. Use "
            "`capabilities` for checked/unchecked scope, refusal mappings, "
            "the metadata-only observability schema, and the exact release "
            "tuple."),
        "mcp": {
            "command": "python3 -m srdcheck.mcp",
            "transport": "stdio",
            "protocolVersion": PROTOCOL_VERSION,
            "tools": [t["name"] for t in tools],
            "notes": (
                "Zero-dependency stdlib MCP server. Tool descriptions/schemas "
                "are supplied by loaded adapters (queries.json). Verdicts "
                "arrive as structuredContent; illegal and cannot-adjudicate "
                "are results, not protocol errors. The opt-in table_evaluation "
                "tool projects one native query without changing native tool "
                "response schemas. Set SRDCHECK_TRACE=stderr and pass an "
                "optional request_id for out-of-band metadata-only tracing."),
        },
        "_generated_by": "scripts/gen_tool_json.py",
    }


def render():
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    (ROOT / "tool.json").write_text(render(), encoding="utf-8")
    n = len(build()["mcp"]["tools"])
    print(f"wrote tool.json — version {__version__}, {n} MCP tools")
