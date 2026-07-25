"""The drift oracle (issue #11): every key a handler reads must be declared in
its query's inputSchema — so the silent-param-swallow bug class cannot be
reintroduced. Static source scan; no model, no execution."""
import inspect
import re

from srdcheck.adapter import Adapter
import srdcheck.adapters  # noqa: F401
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
AD = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"
spec = importlib.util.spec_from_file_location("h521", AD / "handlers.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)

import json
QUERIES = json.loads((AD / "queries.json").read_text())

KEY = re.compile(r'\b(p|atk|tgt)(?:\.get\(|\[)"([a-z_0-9-]+)"')
VAR_TO_PROP = {"p": None, "atk": "attacker", "tgt": "target"}


def reads_of(fn):
    src = inspect.getsource(fn)
    return {(var, key) for var, key in KEY.findall(src)}


def declared(query_type):
    schema = (QUERIES.get(query_type) or {}).get("inputSchema") or {}
    props = schema.get("properties") or {}
    top = set(props)
    nested = {name: set((p.get("properties") or {}))
              for name, p in props.items() if isinstance(p, dict)}
    return top, nested


def test_every_handler_read_is_declared():
    failures = []
    for qtype, fn in H.HANDLERS.items():
        top, nested = declared(qtype)
        if not top:
            continue  # schema declares no properties -> validation is off for it
        for var, key in reads_of(fn):
            if key.startswith("_"):
                continue  # handler-internal plumbing keys, not caller surface
            prop = VAR_TO_PROP[var]
            if prop is None:
                if key not in top:
                    failures.append(f"{qtype}: reads undeclared top-level '{key}'")
            else:
                if prop in nested and nested[prop] and key not in nested[prop]:
                    failures.append(f"{qtype}: reads undeclared '{prop}.{key}'")
    assert not failures, "schema drift:\n  " + "\n  ".join(sorted(failures))
