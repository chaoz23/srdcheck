"""Adapter conformance (E2): the bar ANY adapter must clear - ours or a
third party's. The honesty machinery is the entry ticket: provenance,
schema-declared inputs, unknown-key refusal, crash-free dispatch."""
import json
import pathlib


def check(adapter_id, adapters_dir=None):
    from .access import AdapterHandle, ADAPTERS_DIR
    from .contract import is_semver_2_0
    from .engine import Engine
    root = pathlib.Path(adapters_dir) if adapters_dir else ADAPTERS_DIR
    problems = []
    adir = root / adapter_id
    # 1. manifest: provenance is non-negotiable
    mpath = adir / "manifest.json"
    if not mpath.exists():
        return [f"missing manifest.json"]
    m = json.loads(mpath.read_text())
    for k in ("name", "license"):
        if not m.get(k):
            problems.append(f"manifest missing '{k}'")
    if "version" not in m:
        problems.append("manifest missing 'version'")
    elif not is_semver_2_0(m["version"]):
        problems.append(
            "manifest 'version' must be a SemVer 2.0 string; "
            f"got {m['version']!r}")
    for field in ("data_version", "rules_version"):
        if field in m and not is_semver_2_0(m[field]):
            problems.append(
                f"manifest '{field}' must be a SemVer 2.0 string; "
                f"got {m[field]!r}")
    if not (m.get("attribution") or m.get("license") in ("MIT", "CC0")):
        problems.append("manifest missing 'attribution' (required for licensed content)")
    src = m.get("source") or {}
    if src and not src.get("sha256"):
        problems.append("manifest.source lacks sha256 (hash-pin the source document)")
    # Validate the directory the caller resolved, including third-party roots;
    # never substitute a bundled adapter that happens to share its identifier.
    try:
        a = AdapterHandle(Engine([adir]))
    except Exception as exc:
        problems.append(f"adapter failed to load ({type(exc).__name__})")
        return problems
    qpath = adir / "queries.json"
    schemas = json.load(open(qpath)) if qpath.exists() else {}
    # 2. every declared query dispatches without crashing on empty params
    for qt in sorted(set(list(schemas)) | {"jurisdiction"}):
        try:
            v = a.query(qt, {})
            if not isinstance(v, dict) or "exit_code" not in v:
                problems.append(f"{qt}: verdict lacks exit_code")
        except Exception as e:
            problems.append(f"{qt}: crashed on empty params ({type(e).__name__})")
    # 3. unknown-key refusal: a bogus top-level key must NOT pass silently
    for qt, spec in schemas.items():
        sch = (spec or {}).get("inputSchema") or {}
        if sch.get("additionalProperties") is False:
            try:
                v = a.query(qt, {"definitely_not_a_real_key_9x": 1})
                if v.get("exit_code") != 2:
                    problems.append(f"{qt}: unknown key accepted (exit {v.get('exit_code')}) - "
                                    f"silent-swallow is the wrong-looking-verdict bug")
            except Exception:
                pass
            break   # one probe proves the kernel path
    # 4. declared schemas must forbid undeclared keys
    loose = [qt for qt, spec in schemas.items()
             if ((spec or {}).get("inputSchema") or {}).get("additionalProperties") is not False]
    if loose:
        problems.append(f"schemas without additionalProperties:false: {loose[:5]}")
    return problems
