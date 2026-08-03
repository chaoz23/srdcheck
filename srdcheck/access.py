"""Stable, versioned public API for consuming a loaded adapter's content
(issue #5): a supported way in that does not couple callers to internal file
paths. Content-neutral by design — this layer knows about adapters, categories,
and records, never about any particular ruleset's vocabulary.

Adapter identifiers are versioned (e.g. "srd-5.2.1"); a future version ships as
another loadable identifier (e.g. "srd-5.1"), so the version is first-class and
new versions slot in without a breaking change.

    from srdcheck import load_adapter, available_adapters

    a = load_adapter("srd-5.2.1")   # a versioned identifier
    a.version                       # the adapter version string
    a.categories()                  # the content categories this adapter carries
    a.names(category)               # the names within a category
    a.record(category, name)        # a fact record for a named entity, or None
    a.query(query_type, params)     # run a query; returns a verdict dict
"""

import hashlib
import json
import pathlib

from . import verdict as v
from .engine import Engine

ADAPTERS_DIR = pathlib.Path(__file__).resolve().parent / "adapters"
CLAIMS_PATH = pathlib.Path(__file__).resolve().parent / "capability_claims.json"


def available_adapters():
    """Versioned identifiers of the bundled adapters."""
    return sorted(p.name for p in ADAPTERS_DIR.iterdir()
                  if (p / "manifest.json").exists())


def default_adapter_paths():
    """Adapter dirs the default engine loads — every bundled adapter except
    those whose manifest sets "default_load": false (e.g. a reference/older
    version kept loadable-on-demand so it doesn't blur the primary ruleset)."""
    out = []
    for p in sorted(ADAPTERS_DIR.iterdir()):
        m = p / "manifest.json"
        if m.exists() and json.loads(m.read_text()).get("default_load", True):
            out.append(p)
    return out


def _adapter_digest(root):
    digest = hashlib.sha256()
    included = {"manifest.json", "entities.json", "queries.json",
                "spell_facts.json", "state_schema.json",
                "condition_dependencies.json",
                "handlers.py"}
    paths = [p for p in root.rglob("*")
             if p.is_file() and (p.name in included or "atoms" in p.parts
                                 or ("sources" in p.parts and p.suffix == ".txt"))]
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def capabilities():
    """Machine-readable engine and bundled-adapter capability contract."""
    from . import __version__
    from .contract import (CAPABILITIES_SCHEMA_VERSION, COMPATIBILITY_WINDOW,
                           VERDICT_SCHEMA_VERSION, WHY_STABILITY,
                           supported_engine_minors)
    from .mcp import PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
    claims = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))
    refusal_contract = v.refusal_contract()
    adapters = []
    tool_names = {"jurisdiction", "table_evaluation"}
    for identifier in available_adapters():
        root = ADAPTERS_DIR / identifier
        manifest = json.loads((root / "manifest.json").read_text())
        queries_path = root / "queries.json"
        queries = json.loads(queries_path.read_text()) if queries_path.exists() else {}
        if manifest.get("default_load", True):
            tool_names.update(q.replace(".", "_").replace("-", "_") for q in queries)
        adapters.append({
            "identifier": identifier,
            "name": manifest["name"],
            "version": manifest["version"],
            "data_version": (manifest["data_version"]
                             if "data_version" in manifest
                             else manifest["version"]),
            "rules_version": (manifest["rules_version"]
                              if "rules_version" in manifest
                              else manifest["version"]),
            "ruleset": manifest.get("ruleset", ""),
            "default_load": manifest.get("default_load", True),
            "digest": _adapter_digest(root),
            "query_types": sorted(queries),
        })
    release_adapters = [
        {key: adapter[key] for key in ("identifier", "version", "data_version",
                                       "rules_version", "digest")}
        for adapter in adapters
    ]
    return {
        "schema_version": CAPABILITIES_SCHEMA_VERSION,
        "engine": {"name": "srdcheck", "version": __version__},
        "machine_contracts": {
            "verdict_schema_version": VERDICT_SCHEMA_VERSION,
            "capabilities_schema_version": CAPABILITIES_SCHEMA_VERSION,
            "refusal_contract_version": refusal_contract["schema_version"],
            "compatibility_window": COMPATIBILITY_WINDOW,
            "supported_engine_minors": supported_engine_minors(__version__),
            "why_stability": WHY_STABILITY,
        },
        "release_tuple": {
            "engine_version": __version__,
            "adapters": release_adapters,
        },
        "mcp_protocol_version": PROTOCOL_VERSION,
        "mcp_supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "adapters": adapters,
        "mcp_tools": sorted(tool_names),
        "refusal_contract": refusal_contract,
        "result_contract": claims["result_contract"],
        "query_coverage": claims["query_coverage"],
        "targets": claims["targets"],
    }


def load_adapter(identifier):
    """Load a bundled adapter by its versioned identifier (e.g. 'srd-5.2.1')."""
    root = ADAPTERS_DIR / identifier
    if not (root / "manifest.json").exists():
        raise ValueError(
            f"no bundled adapter {identifier!r}; available: {available_adapters()}")
    return AdapterHandle(Engine([root]))


class AdapterHandle:
    """A supported handle over one loaded adapter's content and queries."""

    def __init__(self, engine):
        self._engine = engine
        self._a = engine.adapters[0]

    @property
    def id(self):
        return self._a.id

    @property
    def name(self):
        return self._a.manifest["name"]

    @property
    def version(self):
        return self._a.manifest["version"]

    @property
    def manifest(self):
        return dict(self._a.manifest)

    def categories(self):
        """The content categories this adapter carries."""
        return sorted(self._a.entities_by_category)

    def entities(self, category):
        """Full entries for a category (records where the adapter carries facts,
        bare name strings otherwise)."""
        return list(self._a.entities_by_category.get(category, []))

    def names(self, category):
        """Just the names for a category."""
        return [e["name"] if isinstance(e, dict) else e
                for e in self.entities(category)]

    def record(self, category, name):
        """The fact record for a named entity, or None. Case-insensitive."""
        return self._a.entity_record(category, name)

    def query_types(self):
        return sorted(self._a.query_types)

    def query(self, query_type, params=None, *, asserted_facts=None,
              table_decision=None):
        """Run a query and return a provenance-separated verdict receipt."""
        return self._engine.query(
            query_type, params or {}, asserted_facts=asserted_facts,
            table_decision=table_decision).as_dict()


def edition_check(name, category, current="srd-5.2.1", priors=("srd-5.1",)):
    """Cross-version validity: is `name` (a `category` entity) valid in the
    `current` ruleset version, an edition trap (present in a `prior` version but
    not the current one), or unknown? Caller-parameterized — the versions are
    identifiers; no ordering is assumed. Content-neutral: `category` is data.

    Returns the standard verdict: legal (in current) / illegal (an edition trap,
    with the prior version + citation, plus heuristic candidates in current) /
    cannot-adjudicate (in neither — a typo, third-party, or homebrew).
    """
    if not isinstance(name, str) or not name.strip():
        return v.cannot_adjudicate(
            "Edition-check name must be a non-empty string.",
            reason_code="invalid-input", missing_inputs=[])
    if not isinstance(category, str) or not category.strip():
        return v.cannot_adjudicate(
            "Edition-check category must be a non-empty string.",
            reason_code="invalid-input", missing_inputs=[])
    key = name.strip().lower()
    cur = load_adapter(current)

    def cite(handle, cat, nm):
        rec = handle.record(cat, nm)
        if rec and rec.get("citation"):
            return [v.Citation(rec["citation"])]
        return [v.Citation(handle.manifest.get("ruleset", handle.id))]

    if key in {n.lower() for n in cur.names(category)}:
        return v.legal(f"'{name}' is valid {category} content in {current}.",
                       cite(cur, category, name), cur.id)
    for pid in priors:
        prior = load_adapter(pid)
        if key in {n.lower() for n in prior.names(category)}:
            candidates = [n for n in cur.names(category)
                          if n.lower().startswith(key + " ")]
            data = {"edition_trap": True, "found_in": pid, "in_current": False}
            if candidates:
                data["candidates_in_current"] = candidates
            why = (f"'{name}' is a {pid} name, not present in {current} — an "
                   "edition trap")
            why += (f"; in {current} see: {', '.join(candidates)}."
                    if candidates else ".")
            return v.illegal(why, cite(prior, category, name), cur.id, data=data)
    return v.cannot_adjudicate(
        f"'{name}' is not a {category} in {current} or {list(priors)} — it may "
        "be a typo, third-party, or homebrew content.", adapter=cur.id,
        reason_code="unsupported-content",
        missing_inputs=[])
