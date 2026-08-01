"""Release truth: installed data, versions, capabilities, and metadata agree."""

import json
import pathlib
import re

import srdcheck
from srdcheck.access import capabilities, default_adapter_paths
from srdcheck.engine import Engine
from srdcheck.mcp import SERVER_INFO

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_packaged_source_text_supports_citations():
    adapter = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"
    source_page = adapter / "sources" / "text" / "page-116.txt"
    assert source_page.exists()
    assert "The target spends its turn moving away" in source_page.read_text()
    verdict = Engine(default_adapter_paths()).cite("Command")
    assert verdict.exit_code == 0
    assert verdict.data["page"] == 116
    assert "The target spends its turn moving away" in verdict.data["text"]


def test_engine_version_is_canonical_everywhere():
    assert SERVER_INFO["version"] == srdcheck.__version__
    server = json.loads((ROOT / "server.json").read_text())
    assert server["version"] == srdcheck.__version__
    assert {package["version"] for package in server["packages"]} == {srdcheck.__version__}
    project = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE)
    assert match and match.group(1) == srdcheck.__version__
    assert f"Status: v{srdcheck.__version__}" in (ROOT / "README.md").read_text()


def test_documented_adapter_versions_match_manifest():
    manifest = json.loads((ROOT / "srdcheck" / "adapters" / "srd-5.2.1" /
                           "manifest.json").read_text())
    examples = "\n".join((ROOT / path).read_text() for path in (
        "README.md", "docs/anatomy-of-a-turn.md"))
    versions = set(re.findall(r'"adapter": "srd-5\.2\.1@([^"]+)"', examples))
    assert versions == {manifest["version"]}


def test_capabilities_distinguish_engine_and_adapters():
    value = capabilities()
    assert value["schema_version"] == "1.0"
    assert value["engine"] == {"name": "srdcheck", "version": srdcheck.__version__}
    adapters = {item["identifier"]: item for item in value["adapters"]}
    assert adapters["srd-5.2.1"]["version"] == "0.2.0"
    assert len(adapters["srd-5.2.1"]["digest"]) == 64
    assert "turn_plan" in value["mcp_tools"]


def test_tool_metadata_matches_live_capabilities():
    tool = json.loads((ROOT / "tool.json").read_text())
    assert tool["version"] == srdcheck.__version__
    assert set(tool["mcp"]["tools"]) == set(capabilities()["mcp_tools"])
    assert "capabilities" in tool["invocation"]["subcommands"]


def test_release_tag_identity_guard():
    import importlib.util
    path = ROOT / "scripts" / "verify_release_identity.py"
    spec = importlib.util.spec_from_file_location("verify_release_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.engine_version() == srdcheck.__version__
    module.verify_tag(f"v{srdcheck.__version__}", srdcheck.__version__)
    try:
        module.verify_tag("v999.0.0", srdcheck.__version__)
    except SystemExit as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("mismatched release tag was accepted")


def test_release_workflows_cover_offline_install_and_registry_smoke():
    cold_smoke = (ROOT / "scripts" / "cold_artifact_smoke.py").read_text()
    assert '"--no-index"' in cold_smoke
    assert '"--no-build-isolation"' in cold_smoke

    registry = (ROOT / ".github" / "workflows" / "registry-smoke.yml").read_text()
    assert "release:" in registry and "types: [published]" in registry
    assert "workflow_dispatch:" in registry
    assert 'srdcheck==$VERSION' in registry
    assert "registry-artifacts/*.whl registry-artifacts/*.tar.gz" in registry


def test_pypi_publish_reuses_only_verified_tag_artifacts():
    publish = (ROOT / ".github" / "workflows" / "publish-pypi.yml").read_text()
    assert "workflow_dispatch:" in publish
    assert "if: github.ref == 'refs/heads/main'" in publish
    assert "id-token: write" in publish
    assert "attestations: read" in publish
    assert "release-artifacts.yml" in publish
    assert 'test "$(jq -r .conclusion' in publish
    assert 'test "$(jq -r .head_branch' in publish
    assert 'test "$(jq -r .head_sha' in publish
    assert "compare/${TAG_SHA}...${GITHUB_SHA}" in publish
    assert '.conclusion == "success"' in publish
    assert '.expired == false' in publish
    assert "sha256sum --check dist/SHA256SUMS" in publish
    assert "gh attestation verify" in publish
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in publish
    assert "packages-dir: publish/" in publish
