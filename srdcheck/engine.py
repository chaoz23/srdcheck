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

    def query(self, query_type, params):
        if query_type == "jurisdiction":
            return self.jurisdiction(params.get("name", ""))
        for a in self.adapters:
            if query_type in a.query_types:
                return a.handle(query_type, params)
        known = sorted(t for a in self.adapters for t in a.query_types)
        return v.cannot_adjudicate(
            f"No loaded adapter answers query type '{query_type}'. "
            f"Available: {', '.join(known)}.",
            adapter=", ".join(a.id for a in self.adapters))
