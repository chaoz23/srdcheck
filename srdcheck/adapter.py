"""Adapter loading. An adapter is a directory containing:

  manifest.json   provenance: name, version, source doc + sha256, license,
                  attribution, and the query types it claims jurisdiction over
  entities.json   {category: [names...]} — the content this adapter knows exists
  atoms/*.json    rule atoms: parameters + citations, consumed by handlers
  handlers.py     query handlers (the game logic; never in the kernel)

The kernel knows the *shape* of these files, never their contents' meaning (T7).
"""

import importlib.util
import json
import pathlib


class Adapter:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text())
        self.id = f"{self.manifest['name']}@{self.manifest['version']}"
        # An entity is either a bare name string or an object with a "name"
        # field plus adapter-defined facts (the kernel stays content-neutral —
        # it indexes names and carries records without interpreting either).
        ents = json.loads((self.root / "entities.json").read_text())
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
        self._handlers = self._load_handlers()

    def _load_handlers(self):
        hp = self.root / "handlers.py"
        if not hp.exists():
            return {}
        spec = importlib.util.spec_from_file_location(
            f"srdcheck_adapter_{self.manifest['name'].replace('-', '_')}", hp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return dict(getattr(mod, "HANDLERS", {}))

    @property
    def query_types(self):
        return set(self._handlers) | {"jurisdiction"}

    def lookup_entity(self, name):
        return self.entities.get(name.strip().lower())

    def entity_record(self, category, name):
        """The full record for an entity that carries facts (e.g. a creature's
        cr/xp/citation), or None. Content-neutral: the kernel does not interpret
        the fields."""
        return self.entity_facts.get((category, name.strip().lower()))

    def handle(self, query_type, params):
        return self._handlers[query_type](self, params)
