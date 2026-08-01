#!/usr/bin/env python3
"""Cold-install release artifacts and exercise public CLI/library/MCP journeys."""

import argparse
import email
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import zipfile


SOURCE_PAGE = "srdcheck/adapters/srd-5.2.1/sources/text/page-116.txt"
ADAPTER_MANIFEST = "srdcheck/adapters/srd-5.2.1/manifest.json"


def run(argv, cwd, *, stdin=None, env=None):
    result = subprocess.run(
        argv, cwd=cwd, input=stdin, text=True, capture_output=True, timeout=120,
        env=env,
    )
    if result.returncode:
        raise SystemExit(
            f"command failed ({result.returncode}): {' '.join(map(str, argv))}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def inspect_artifact(artifact):
    """Prove each archive contains its version, license, and attributed data."""
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            names = archive.namelist()
            payloads = {
                name: archive.read(name)
                for name in names
                if not name.endswith("/")
            }
        read = payloads.__getitem__
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        license_names = [name for name in names
                         if ".dist-info/licenses/" in name]
        member = lambda name: name
    elif artifact.name.endswith(".tar.gz"):
        with tarfile.open(artifact, "r:gz") as archive:
            names = archive.getnames()
            payloads = {
                name: archive.extractfile(name).read()
                for name in names
                if archive.getmember(name).isfile()
            }
        prefix = names[0].rstrip("/") + "/"
        metadata_name = prefix + "PKG-INFO"
        license_names = [prefix + name for name in ("LICENSE", "NOTICE")
                         if prefix + name in names]
        read = payloads.__getitem__
        member = lambda name: prefix + name
    else:
        raise AssertionError(f"unsupported artifact: {artifact}")

    assert any(name.endswith("/LICENSE") for name in license_names), \
        "root MIT license is missing"
    assert any(name.endswith("/NOTICE") for name in license_names), \
        "CC-BY attribution notice is missing"
    assert member(SOURCE_PAGE) in names, "packaged SRD citation text is missing"
    assert member(ADAPTER_MANIFEST) in names, "adapter attribution manifest is missing"
    assert not any(name.endswith(".pdf") for name in names), \
        "source PDFs leaked into artifact"
    assert b"The target spends its turn moving away" in read(member(SOURCE_PAGE))
    manifest = json.loads(read(member(ADAPTER_MANIFEST)))
    assert manifest["license"] == "CC-BY-4.0"
    assert "Wizards of the Coast LLC" in manifest["attribution"]
    metadata = email.message_from_bytes(read(metadata_name))
    assert metadata["Name"] == "srdcheck"
    assert metadata["Version"]
    return metadata["Version"]


def smoke(artifact):
    artifact = artifact.resolve()
    artifact_version = inspect_artifact(artifact)
    with tempfile.TemporaryDirectory(prefix="srdcheck-cold-") as raw:
        root = pathlib.Path(raw)
        site = root / "site"
        outside = root / "outside-checkout"
        outside.mkdir()
        python = pathlib.Path(sys.executable)
        run([
            str(python), "-m", "pip", "install", "--no-deps", "--no-index",
            "--no-build-isolation", "--target", str(site), str(artifact),
        ], outside)
        clean_env = dict(os.environ)
        clean_env["PYTHONPATH"] = str(site)
        clean_env["PYTHONDONTWRITEBYTECODE"] = "1"

        cite = json.loads(run([str(python), "-m", "srdcheck", "cite", "Command"],
                              outside, env=clean_env))
        assert cite["exit_code"] == 0 and cite["data"]["page"] == 116
        assert "The target spends its turn moving away" in cite["data"]["text"]

        jurisdiction = json.loads(run(
            [str(python), "-m", "srdcheck", "jurisdiction", "Fireball"],
            outside, env=clean_env,
        ))
        assert jurisdiction["exit_code"] == 0

        query = json.loads(run(
            [str(python), "-m", "srdcheck", "query", "mage-hand.use",
             '{"kind":"manipulate_object","weight_lb":1,"distance_ft":10}'],
            outside, env=clean_env,
        ))
        assert query["exit_code"] == 0 and query["rule_ids"]

        capabilities = json.loads(run(
            [str(python), "-m", "srdcheck", "capabilities"],
            outside, env=clean_env,
        ))
        assert capabilities["engine"]["version"]
        assert capabilities["engine"]["version"] == artifact_version
        assert "turn_plan" in capabilities["mcp_tools"]

        library = json.loads(run([
            str(python), "-c",
            "import json,srdcheck; a=srdcheck.load_adapter('srd-5.2.1'); "
            "q=a.query('creature.stats',{'name':'Ghast'}); "
            "print(json.dumps({'version':srdcheck.__version__,'xp':a.record('creature','Ghast')['xp'],"
            "'query_xp':q['data']['xp'],"
            "'file':srdcheck.__file__}))",
        ], outside, env=clean_env))
        assert library["version"] == capabilities["engine"]["version"]
        assert library["xp"] == 450
        assert library["query_xp"] == 450
        assert pathlib.Path(library["file"]).is_relative_to(site)

        messages = "".join(json.dumps(item) + "\n" for item in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {
                 "protocolVersion": "2025-06-18",
                 "capabilities": {},
                 "clientInfo": {"name": "artifact-smoke", "version": "1.0"},
             }},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "mage_hand_use", "arguments": {
                 "kind": "manipulate_object", "weight_lb": 1, "distance_ft": 10}}},
        ])
        replies = [json.loads(line) for line in run(
            [str(python), "-m", "srdcheck.mcp"], outside,
            stdin=messages, env=clean_env,
        ).splitlines()]
        by_id = {item["id"]: item for item in replies}
        assert by_id[1]["result"]["serverInfo"]["version"] == library["version"]
        assert all("outputSchema" in tool for tool in by_id[2]["result"]["tools"])
        assert by_id[3]["result"]["structuredContent"]["exit_code"] == 0
    print(f"cold artifact: OK {artifact.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=pathlib.Path)
    args = parser.parse_args()
    for artifact in args.artifacts:
        smoke(artifact)


if __name__ == "__main__":
    main()
