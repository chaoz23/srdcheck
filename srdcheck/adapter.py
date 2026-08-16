"""Adapter loading. An adapter is a directory containing:

  manifest.json   provenance: name, version, source doc + sha256, license,
                  attribution, and the query types it claims jurisdiction over
  entities.json   {category: [names...]} — the content this adapter knows exists
  atoms/*.json    rule atoms: parameters + citations, consumed by handlers
  handlers.py     query handlers (the game logic; never in the kernel), or a
                  handlers/ package exporting the same HANDLERS registry

The kernel knows the *shape* of these files, never their contents' meaning (T7).
"""

import hashlib
import importlib.util
import inspect
import json
import pathlib
import re
import sys
import typing

from .coverage import apply_query_scope

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    from .verdict import Verdict

#: The handler contract every adapter's HANDLERS registry maps to. Positional
#: `(adapter, params)`, returning a Verdict. Enforced at load time by
#: `_validated_handlers` so a malformed registry fails where it is declared,
#: not mid-query with an opaque TypeError.
Handler = typing.Callable[["Adapter", dict], "Verdict"]


class Adapter:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text())
        self.id = f"{self.manifest['name']}@{self.manifest['version']}"
        # Older and third-party adapters may carry only the original aggregate
        # version.  Explicit identities are additive; the aggregate version is
        # the backward-compatible fallback, never a new conformance hurdle.
        self.data_version = (self.manifest["data_version"]
                             if "data_version" in self.manifest
                             else self.manifest["version"])
        self.rules_version = (self.manifest["rules_version"]
                              if "rules_version" in self.manifest
                              else self.manifest["version"])
        # An entity is either a bare name string or an object with a "name"
        # field plus adapter-defined facts (the kernel stays content-neutral —
        # it indexes names and carries records without interpreting either).
        ents = json.loads((self.root / "entities.json").read_text())
        self.entities_by_category = ents
        self.entities = {}
        self.entity_facts = {}
        for category, items in ents.items():
            for item in items:
                name = item["name"] if isinstance(item, dict) else item
                self.entities.setdefault(name.lower(), []).append(category)
                if isinstance(item, dict):
                    self.entity_facts[(category, name.lower())] = item
        self.atoms = {}
        for f in sorted((self.root / "atoms").glob("*.json")):
            for atom in json.loads(f.read_text()):
                self.atoms[atom["id"]] = atom
        qm = self.root / "queries.json"
        self.query_meta = json.loads(qm.read_text()) if qm.exists() else {}
        self._data = {}
        self._handlers = self._load_handlers()

    def data(self, filename):
        """Lazily read and cache an adapter-owned JSON data file, keyed on this
        adapter instance. Content-neutral: the kernel parses the file and never
        interprets it — what the shape means is the adapter's business.

        Handlers use this instead of module-level caches so that adapter data
        cannot outlive its adapter, two adapters cannot share one cache, and
        dropping the Adapter is a complete teardown.

        The cached object is shared, not copied, so callers must treat it as
        read-only.
        """
        if filename not in self._data:
            path = self.root / filename
            self._data[filename] = json.loads(path.read_text(encoding="utf-8"))
        return self._data[filename]

    def _module_name(self):
        """A module name unique to this adapter *path*, not just its name, so
        two versions of one adapter loaded from different roots cannot collide
        in sys.modules."""
        stem = re.sub(r"\W", "_", self.manifest["name"])
        tag = hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:8]
        return f"srdcheck_adapter_{stem}_{tag}"

    def _handler_spec(self, name):
        """Handlers are either one `handlers.py` (the simple path the adapter
        spec documents) or a `handlers/` package (for adapters whose rule
        domains have outgrown a single file). Both must export HANDLERS."""
        pkg = self.root / "handlers" / "__init__.py"
        if pkg.exists():
            return importlib.util.spec_from_file_location(
                name, pkg,
                submodule_search_locations=[str(self.root / "handlers")])
        single = self.root / "handlers.py"
        if single.exists():
            return importlib.util.spec_from_file_location(name, single)
        return None

    def _load_handlers(self):
        name = self._module_name()
        spec = self._handler_spec(name)
        if spec is None:
            return {}
        mod = importlib.util.module_from_spec(spec)
        # Registered before exec so intra-package (`from . import ...`) imports
        # resolve; dropped again on failure so a broken adapter leaves nothing
        # half-initialised behind for the next load to find.
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        return self._validated_handlers(getattr(mod, "HANDLERS", {}))

    def _validated_handlers(self, handlers):
        """A registry is a contract, so check it where it is declared. An
        adapter that ships a non-callable or a wrong-arity handler should fail
        at load with the offending query type named, not at query time."""
        if not isinstance(handlers, dict):
            raise TypeError(
                f"{self.root.name}: HANDLERS must be a dict of "
                f"{{query_type: fn(adapter, params)}}, got "
                f"{type(handlers).__name__}")
        for query_type, fn in sorted(handlers.items()):
            where = f"{self.root.name}: handler for '{query_type}'"
            if not callable(fn):
                raise TypeError(f"{where} is not callable ({type(fn).__name__})")
            try:
                inspect.signature(fn).bind(self, {})
            except TypeError as exc:
                raise TypeError(
                    f"{where} does not accept (adapter, params): {exc}") from exc
        return dict(handlers)

    @property
    def query_types(self):
        return set(self._handlers) | {"jurisdiction"}

    def cite(self, name):
        """Verbatim source text block for a named heading (issue #14).
        Provenance surface: returns the page's own text, never interpretation."""
        import re
        tdir = self.root / "sources" / "text"
        if not tdir.exists():
            return None
        pat = re.compile(rf"^(?:[A-Z][A-Za-z' ]*: )?{re.escape(name)}\s*$",
                         re.M | re.I)
        for p in sorted(tdir.glob("page-*.txt")):
            t = p.read_text()
            m = pat.search(t)
            if not m:
                continue
            page = int(p.stem.replace("page-", ""))
            block = t[m.start():m.start() + 1700]
            cut = block.rfind(".")
            return {"page": page, "text": block[:cut + 1] if cut > 0 else block}
        return None

    def lookup_entity(self, name):
        return self.entities.get(name.strip().lower())

    def entity_record(self, category, name):
        """The full record for an entity that carries facts (e.g. a creature's
        cr/xp/citation), or None. Content-neutral: the kernel does not interpret
        the fields."""
        return self.entity_facts.get((category, name.strip().lower()))

    def handle(self, query_type, params):
        from .verdict import with_provenance
        result = apply_query_scope(
            self._handlers[query_type](self, params),
            self.manifest["name"], query_type)
        return with_provenance(result, params)
