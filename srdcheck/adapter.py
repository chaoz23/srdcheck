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
        ents = json.loads((self.root / "entities.json").read_text())
        self.entities = {}
        for category, names in ents.items():
            for n in names:
                self.entities.setdefault(n.lower(), []).append(category)
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

    def handle(self, query_type, params):
        return self._handlers[query_type](self, params)
