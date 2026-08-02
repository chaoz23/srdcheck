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


def run(argv, cwd, *, stdin=None, env=None, allowed_returncodes=(0,)):
    result = subprocess.run(
        argv, cwd=cwd, input=stdin, text=True, encoding="utf-8",
        capture_output=True, timeout=120, env=env,
    )
    if result.returncode not in allowed_returncodes:
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
        assert prefix + "docs/support-matrix.md" in names, (
            "source distribution omits the published support contract"
        )
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
    base_requirements = [
        requirement for requirement in metadata.get_all("Requires-Dist", [])
        if "extra ==" not in requirement
    ]
    assert not base_requirements, (
        "the documented zero-dependency runtime acquired base requirements: "
        + ", ".join(base_requirements)
    )
    return metadata["Version"]


def console_entrypoints(site, platform_name=None):
    """Locate both project.scripts launchers from a ``--target`` install.

    pip builds the target through its active ``home`` installation scheme, so
    the launcher directory is not safely derivable from ``os.name`` alone.
    Require the real launchers, but discover the two valid scheme directories
    instead of predicting one.
    """
    windows = (platform_name or os.name) == "nt"
    directories = ((site / "Scripts", site / "bin", site) if windows
                   else (site / "bin", site / "Scripts", site))
    suffixes = (".exe", "") if windows else ("", ".exe")

    def locate(command):
        candidates = [directory / f"{command}{suffix}"
                      for directory in directories for suffix in suffixes]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        rendered = ", ".join(str(path) for path in candidates)
        raise AssertionError(
            f"installed {command} entry point is missing; checked: {rendered}")

    return locate("srdcheck"), locate("srdcheck-mcp")


def smoke(artifact):
    artifact = artifact.resolve()
    artifact_version = inspect_artifact(artifact)
    with tempfile.TemporaryDirectory(prefix="srdcheck-cold-") as raw:
        root = pathlib.Path(raw)
        # Spaces and non-ASCII path components are intentional. This same
        # public-artifact smoke runs on Windows, macOS, and Ubuntu, so it also
        # guards path handling rather than only proving a friendly POSIX path.
        site = root / "installed rules Ω"
        outside = root / "outside checkout — café 玩家"
        outside.mkdir()
        python = pathlib.Path(sys.executable)
        utf8_env = dict(os.environ)
        utf8_env["PYTHONUTF8"] = "1"
        run([
            str(python), "-m", "pip", "install", "--no-deps", "--no-index",
            "--no-build-isolation", "--target", str(site), str(artifact),
        ], outside, env=utf8_env)
        clean_env = dict(utf8_env)
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

        unicode_name = "Café Familiar Ω"
        unknown = json.loads(run(
            [str(python), "-m", "srdcheck", "jurisdiction", unicode_name],
            outside, env=clean_env, allowed_returncodes=(2,),
        ))
        assert unknown["exit_code"] == 2
        assert unicode_name in unknown["why"]

        query = json.loads(run(
            [str(python), "-m", "srdcheck", "query", "mage-hand.use",
             '{"kind":"manipulate_object","weight_lb":1,"distance_ft":10}'],
            outside, env=clean_env,
        ))
        assert query["exit_code"] == 0 and query["rule_ids"]

        shared = json.loads(run(
            [str(python), "-m", "srdcheck", "query", "mage-hand.use",
             '{"kind":"attack"}', "--table-evaluation"],
            outside, env=clean_env, allowed_returncodes=(1,),
        ))
        assert shared["schema_version"] == "table.evaluation/1.0"
        assert shared["status"] == "findings"
        assert shared["authority_status"] == "self_attested"
        assert "mage-hand.cant-attack" in shared["findings"][0]["evidence_refs"]

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

        messages = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in [
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
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "jurisdiction", "arguments": {
                 "name": unicode_name}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "table_evaluation", "arguments": {
                 "query_type": "mage-hand.use", "params": {"kind": "attack"},
                 "context": {"session_id": "artifact-session",
                             "correlation_id": "artifact-call"}}}},
        ])
        replies = [json.loads(line) for line in run(
            [str(python), "-m", "srdcheck.mcp"], outside,
            stdin=messages, env=clean_env,
        ).splitlines()]
        by_id = {item["id"]: item for item in replies}
        assert by_id[1]["result"]["serverInfo"]["version"] == library["version"]
        assert all("outputSchema" in tool for tool in by_id[2]["result"]["tools"])
        assert by_id[3]["result"]["structuredContent"]["exit_code"] == 0
        assert by_id[4]["result"]["structuredContent"]["exit_code"] == 2
        assert unicode_name in by_id[4]["result"]["structuredContent"]["why"]
        projected = by_id[5]["result"]["structuredContent"]
        assert projected["status"] == "findings"
        assert projected["authority_status"] == "self_attested"
        assert projected["subject"]["session_id"] == "artifact-session"
        assert "correlation:artifact-call" in projected["subject"]["entity_refs"]

        # --target places project.scripts launchers beneath the target itself.
        # Invoke them directly so Windows .exe wrappers and both entry-point
        # declarations are covered, not just the equivalent `python -m` paths.
        cli_entry, mcp_entry = console_entrypoints(site)
        cli_payload = json.loads(run(
            [str(cli_entry), "jurisdiction", "Fireball"], outside,
            env=clean_env,
        ))
        assert cli_payload["exit_code"] == 0

        entry_replies = [json.loads(line) for line in run(
            [str(mcp_entry)], outside, stdin=messages, env=clean_env,
        ).splitlines()]
        entry_by_id = {item["id"]: item for item in entry_replies}
        assert (entry_by_id[1]["result"]["serverInfo"]["version"]
                == library["version"])
        assert entry_by_id[3]["result"]["structuredContent"]["exit_code"] == 0
        assert entry_by_id[4]["result"]["structuredContent"]["exit_code"] == 2
    print(f"cold artifact: OK {artifact.name}")


def discover_artifacts(inputs):
    """Expand artifact files or directories without relying on shell globs.

    GitHub Actions uses different default shells on Windows and Unix. Accepting
    a directory lets every CI lane invoke the exact same portable command.
    """
    found = []
    for item in inputs:
        if item.is_dir():
            found.extend(sorted(
                path for path in item.iterdir()
                if path.suffix == ".whl" or path.name.endswith(".tar.gz")
            ))
        else:
            found.append(item)
    unique = []
    seen = set()
    for artifact in found:
        resolved = artifact.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    if not unique:
        raise SystemExit("no wheel or sdist artifacts found")
    return unique


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "artifacts", nargs="+", type=pathlib.Path,
        help="wheel/sdist files or directories containing them",
    )
    args = parser.parse_args()
    for artifact in discover_artifacts(args.artifacts):
        smoke(artifact)


if __name__ == "__main__":
    main()
