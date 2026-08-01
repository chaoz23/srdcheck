"""Query dispatch and the jurisdiction gate.

Every query passes the gate first: if no loaded adapter claims the query
type, or the entity named isn't in any adapter's registry, the answer is an
honest exit 2 — never a guess (T1, T8).
"""

from . import verdict as v
from .adapter import Adapter
from .schema import errors as schema_errors

JURISDICTION_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "minLength": 1}},
    "required": ["name"],
    "additionalProperties": False,
}


class Engine:
    def __init__(self, adapter_paths):
        self.adapters = [Adapter(p) for p in adapter_paths]

    def jurisdiction(self, name):
        if not isinstance(name, str) or not name.strip():
            return v.cannot_adjudicate(
                "Invalid input: name must be a non-empty string.",
                data={"validation_errors": ["$.name: expected a non-empty string"]})
        for a in self.adapters:
            cats = a.lookup_entity(name)
            if cats:
                categories = sorted(set(cats))
                return v.legal(
                    f"'{name}' is known content: {', '.join(categories)}.",
                    adapter=a.id,
                    data={"categories": categories})
        known = ", ".join(a.id for a in self.adapters)
        return v.cannot_adjudicate(
            f"'{name}' is not present in any loaded ruleset ({known}). "
            "Unknown or third-party content cannot be adjudicated.",
            adapter=known)

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
            problems = schema_errors(params, JURISDICTION_INPUT_SCHEMA)
            if problems:
                return self._invalid_input(problems)
            return self.jurisdiction(params["name"])
        for a in self.adapters:
            if query_type in a.query_types:
                schema = (a.query_meta.get(query_type) or {}).get("inputSchema")
                problems = schema_errors(params, schema)
                if problems:
                    return self._invalid_input(problems, a.id)
                return a.handle(query_type, params)
        known = sorted(t for a in self.adapters for t in a.query_types)
        return v.cannot_adjudicate(
            f"No loaded adapter answers query type '{query_type}'. "
            f"Available: {', '.join(known)}.",
            adapter=", ".join(a.id for a in self.adapters))

    @staticmethod
    def _invalid_input(problems, adapter=""):
        unknown = [problem.split(":", 1)[0].removeprefix("$.")
                   for problem in problems if problem.endswith("field is not allowed")]
        data = {"validation_errors": problems}
        if unknown:
            data["unknown_fields"] = unknown
        return v.cannot_adjudicate(
            "Invalid input; correct the request before adjudication: "
            + "; ".join(problems),
            adapter=adapter,
            data=data,
        )
