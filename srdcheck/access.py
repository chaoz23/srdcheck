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

import json
import pathlib

from . import verdict as v
from .engine import Engine

ADAPTERS_DIR = pathlib.Path(__file__).resolve().parent / "adapters"


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

    def query(self, query_type, params=None):
        """Run a query through this adapter; returns the verdict as a dict."""
        return self._engine.query(query_type, params or {}).as_dict()


def edition_check(name, category, current="srd-5.2.1", priors=("srd-5.1",)):
    """Cross-version validity: is `name` (a `category` entity) valid in the
    `current` ruleset version, an edition trap (present in a `prior` version but
    not the current one), or unknown? Caller-parameterized — the versions are
    identifiers; no ordering is assumed. Content-neutral: `category` is data.

    Returns the standard verdict: legal (in current) / illegal (an edition trap,
    with the prior version + citation, plus heuristic candidates in current) /
    cannot-adjudicate (in neither — a typo, third-party, or homebrew).
    """
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
        "be a typo, third-party, or homebrew content.", adapter=cur.id)
