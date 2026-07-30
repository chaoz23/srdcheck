#!/usr/bin/env python3
"""Golden-verdict corpus (E2/M1): pin every adapter's behavior byte-for-byte
BEFORE any kit refactor. For each adapter x query type: an empty-params call
and a required-stubs call. Any future change to any committed verdict fails
CI loudly - refactors must be invisible to consumers."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from srdcheck.access import available_adapters, load_adapter

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/golden"

def stub(schema):
    """Deterministic minimal params from an inputSchema."""
    out = {}
    for k in (schema or {}).get("required", []):
        p = schema["properties"].get(k, {})
        if "enum" in p: out[k] = p["enum"][0]
        elif p.get("type") == "integer": out[k] = 2
        elif p.get("type") == "number": out[k] = 3.0
        elif p.get("type") == "boolean": out[k] = True
        elif p.get("type") == "object": out[k] = {}
        elif p.get("type") == "array": out[k] = []
        else: out[k] = "Test Name"
    return out

def main(check=False):
    drift = []
    for aid in available_adapters():
        a = load_adapter(aid)
        qpath = ROOT / "srdcheck/adapters" / aid / "queries.json"
        schemas = json.load(open(qpath)) if qpath.exists() else {}
        types = sorted(set(list(schemas)) | {"jurisdiction"})
        for qt in types:
            sch = (schemas.get(qt) or {}).get("inputSchema")
            variants = {"empty": {}, "stub": stub(sch) if sch else {"name": "Test Name"}}
            for vname, params in variants.items():
                try:
                    verdict = a.query(qt, params)
                except Exception as e:
                    verdict = {"golden_exception": type(e).__name__, "msg": str(e)[:200]}
                d = OUT / aid
                d.mkdir(parents=True, exist_ok=True)
                f = d / f"{qt.replace('.','_')}__{vname}.json"
                blob = json.dumps(verdict, indent=1, sort_keys=True)
                if check:
                    if not f.exists() or f.read_text() != blob:
                        drift.append(str(f.relative_to(ROOT)))
                else:
                    f.write_text(blob)
    if check and drift:
        print("GOLDEN DRIFT:", *drift[:20], sep="\n  "); sys.exit(1)
    print("golden: OK" if check else f"golden: written for {len(available_adapters())} adapters")

if __name__ == "__main__":
    main(check="--check" in sys.argv)
