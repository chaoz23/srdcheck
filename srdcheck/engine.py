"""Query dispatch and the jurisdiction gate.

Every query passes the gate first: if no loaded adapter claims the query
type, or the entity named isn't in any adapter's registry, the answer is an
honest exit 2 — never a guess (T1, T8).
"""

from . import verdict as v
from .adapter import Adapter


class Engine:
    def __init__(self, adapter_paths):
        self.adapters = [Adapter(p) for p in adapter_paths]

    def jurisdiction(self, name):
        for a in self.adapters:
            cats = a.lookup_entity(name)
            if cats:
                return v.legal(
                    f"'{name}' is known content: {', '.join(sorted(set(cats)))}.",
                    adapter=a.id)
        known = ", ".join(a.id for a in self.adapters)
        return v.cannot_adjudicate(
            f"'{name}' is not present in any loaded ruleset ({known}). "
            "Unknown or third-party content cannot be adjudicated.",
            adapter=known)

    @staticmethod
    def _unknown_fields(params, schema, prefix=""):
        """Recursively collect keys the schema does not declare. Only enforced
        where the schema declares properties; object-typed params without
        declared properties (e.g. open state blobs) are left alone."""
        props = (schema or {}).get("properties")
        if not props or not isinstance(params, dict):
            return []
        unknown = [f"{prefix}{k}" for k in params if k not in props]
        for k, v in params.items():
            if k in props and isinstance(v, dict):
                unknown += Engine._unknown_fields(v, props[k], f"{prefix}{k}.")
        return unknown

    def cite(self, name):
        for a in self.adapters:
            hit = a.cite(name)
            if hit:
                return v.legal(
                    f"Verbatim source text for '{name}' (p.{hit['page']}).",
                    adapter=a.id, data=hit)
        known = ", ".join(a.id for a in self.adapters)
        return v.cannot_adjudicate(
            f"'{name}' not found as a heading in any loaded ruleset's source "
            f"text ({known}).", adapter=known)

    def query(self, query_type, params):
        if query_type == "jurisdiction":
            return self.jurisdiction(params.get("name", ""))
        for a in self.adapters:
            if query_type in a.query_types:
                schema = (a.query_meta.get(query_type) or {}).get("inputSchema")
                unknown = self._unknown_fields(params or {}, schema)
                if unknown:
                    declared = sorted((schema or {}).get("properties", {}))
                    return v.cannot_adjudicate(
                        f"Unknown field(s) {unknown} — not in this query's schema. "
                        f"Declared fields: {', '.join(declared)}. A misspelled field "
                        "must refuse, not silently default (a wrong-looking verdict "
                        "is as bad as a wrong verdict).",
                        adapter=a.id, data={"unknown_fields": unknown})
                return a.handle(query_type, params)
        known = sorted(t for a in self.adapters for t in a.query_types)
        return v.cannot_adjudicate(
            f"No loaded adapter answers query type '{query_type}'. "
            f"Available: {', '.join(known)}.",
            adapter=", ".join(a.id for a in self.adapters))
