"""`srdcheck new-adapter <name>`: scaffold a conformant adapter skeleton."""
import json, pathlib

MANIFEST = {"name": None, "version": "0.1.0", "data_version": "0.1.0",
            "rules_version": "0.1.0", "license": "TODO-SPDX-ID",
            "attribution": "TODO: the attribution your content license requires",
            "source": {"url": "TODO", "sha256": "TODO: hash-pin the source document"}}
QUERIES = {"example.query": {
    "description": "TODO: what this answers, what it refuses, and why.",
    "inputSchema": {"type": "object", "additionalProperties": False,
                    "properties": {"name": {"type": "string"}}, "required": ["name"]}}}
HANDLERS = '''from srdcheck import verdict as v


def example_query(adapter, p):
    """TODO. Honesty contract: refuse (exit 2) what this adapter does not
    cover; a wrong-LOOKING verdict is as bad as a wrong verdict."""
    return v.cannot_adjudicate("not implemented yet", adapter=adapter.id)


HANDLERS = {"example.query": example_query}
'''

def new_adapter(name, dest="."):
    d = pathlib.Path(dest) / name
    (d / "atoms").mkdir(parents=True, exist_ok=True)
    (d / "sources").mkdir(exist_ok=True)
    m = dict(MANIFEST); m["name"] = name
    (d / "manifest.json").write_text(json.dumps(m, indent=1))
    (d / "queries.json").write_text(json.dumps(QUERIES, indent=1))
    (d / "handlers.py").write_text(HANDLERS)
    (d / "entities.json").write_text("{}")
    (d / "README.md").write_text(
        f"# {name} adapter\n\nSee docs/ADAPTER-GUIDE.md in srdcheck. Ship gates:\n"
        f"1. `srdcheck conformance {name}` passes.\n"
        f"2. Registries census-anchored against an independent count of the source.\n"
        f"3. Rebuild reproducibility: one script reproduces every committed artifact.\n"
        f"4. Golden verdicts committed (scripts/build_golden.py pattern).\n")
    return str(d)
