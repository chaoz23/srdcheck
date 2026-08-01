"""Generated capability truth and public-claim guards (#30)."""

import json
import pathlib
import subprocess
import sys

from scripts.capability_map import render_json, render_markdown
from srdcheck.access import capabilities, default_adapter_paths
from srdcheck.adapter import Adapter
from srdcheck.contract import CLAIMS_SCHEMA_VERSION


ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_claim_source_covers_every_shipped_query_exactly_once():
    caps = capabilities()
    entries = caps["query_coverage"]
    actual = [(entry["adapter"], entry["query_type"]) for entry in entries]
    expected = [("kernel", "jurisdiction")]
    for root in default_adapter_paths():
        adapter = Adapter(root)
        expected.extend((adapter.manifest["name"], query_type)
                        for query_type in adapter.query_meta)
    assert len(actual) == len(set(actual))
    assert set(actual) == set(expected)
    evidence_nodes = []
    for entry in entries:
        assert entry["capability"]
        assert entry["checked_scope"]
        assert entry["unchecked_scope"]
        assert entry["evidence"]
        for evidence in entry["evidence"]:
            assert "::" in evidence, f"claim evidence must be a pytest node: {evidence}"
            path = evidence.split("::", 1)[0]
            assert (ROOT / path).exists(), f"missing claim evidence: {evidence}"
            evidence_nodes.append(evidence)
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         *evidence_nodes], cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == 0, collected.stdout + collected.stderr
    actual_nodes = {line.strip() for line in collected.stdout.splitlines()
                    if line.startswith("tests/") and "::" in line}
    assert set(evidence_nodes) <= actual_nodes


def test_target_claims_are_unambiguously_not_shipped():
    source = json.loads((ROOT / "srdcheck/capability_claims.json").read_text())
    assert source["schema_version"] == CLAIMS_SCHEMA_VERSION
    assert source["targets"]
    assert all(target["status"] == "target" for target in source["targets"])
    assert all(target["not_shipped"] for target in source["targets"])
    assert "whether human or agent" in source["result_contract"][
        "authority_boundary"]
    tool_card = json.loads((ROOT / "tool.json").read_text())
    assert "agent-DM" in tool_card["description"]


def test_generated_capability_maps_are_fresh():
    assert (ROOT / "docs/capability-map.json").read_text() == render_json(), (
        "capability-map.json is stale; run python3 scripts/capability_map.py")
    assert (ROOT / "docs/capability-map.md").read_text() == render_markdown(), (
        "capability-map.md is stale; run python3 scripts/capability_map.py")
    machine_map = json.loads((ROOT / "docs/capability-map.json").read_text())
    assert "srdcheck/capability_claims.json" in machine_map["generated_from"]
    assert sorted(item["tool"] for item in machine_map["shipped"]) == sorted(
        capabilities()["mcp_tools"]), "generated tool inventory is incomplete"


def test_anatomy_separates_executable_behavior_from_targets():
    anatomy = (ROOT / "docs/anatomy-of-a-turn.md").read_text()
    assert "## Executable today" in anatomy
    assert "## Target architecture — not shipped" in anatomy
    current = anatomy.split("## Target architecture — not shipped", 1)[0]
    for unsupported_claim in (
            "enumerates every legal move", "stamps level-ups",
            "four end-triggers armed", "Long Jump covers",
            "with the legal spots"):
        assert unsupported_claim not in current
    assert "agent-DM" in current
    assert "Per-result scope fields are not part" in current.replace("\n", " ")


def test_public_claims_do_not_promise_citations_on_boundary_refusals():
    for relative in ("README.md", "llms.txt", "docs/product-truths.md",
                     "docs/anatomy-of-a-turn.md", "docs/adapter-spec.md",
                     "docs/ADAPTER-GUIDE.md", "CONTRIBUTING.md", "tool.json",
                     "server.json"):
        text = (ROOT / relative).read_text().lower()
        for overclaim in ("every verdict carries citations",
                          "every verdict carries verbatim",
                          "every verdict carries its chain",
                          "categories in payload",
                          "exactly one call to make",
                          "all 15 are fully modeled",
                          "sub-millisecond"):
            assert overclaim not in text, relative


def test_release_tuple_separates_adapter_data_and_rules_versions():
    caps = capabilities()
    by_id = {item["identifier"]: item
             for item in caps["release_tuple"]["adapters"]}
    advertised = {item["identifier"]: item for item in caps["adapters"]}
    for identifier, release in by_id.items():
        assert release["version"] == advertised[identifier]["version"]
        assert release["data_version"] == advertised[identifier]["data_version"]
        assert release["rules_version"] == advertised[identifier]["rules_version"]
    assert all(item["digest"] for item in by_id.values())


def test_explicit_tuple_fields_are_additive_for_external_adapters(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "name": "legacy-external", "version": "7.4.2", "license": "MIT"}))
    (tmp_path / "entities.json").write_text("{}")
    adapter = Adapter(tmp_path)
    assert adapter.data_version == "7.4.2"
    assert adapter.rules_version == "7.4.2"
