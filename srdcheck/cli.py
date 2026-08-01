"""srdcheck CLI.

  python -m srdcheck jurisdiction "<name>"
  python -m srdcheck query <query-type> '<params-json>'
  python -m srdcheck edition-check "<name>" [--category creature] [--current srd-5.2.1] [--prior srd-5.1]
  python -m srdcheck conformance <adapter-id>   # the bar any adapter must clear
  python -m srdcheck new-adapter <name>         # scaffold a conformant skeleton
  python -m srdcheck capabilities               # versions, digests, protocol, tools
  python -m srdcheck --schema
  echo '{"type": "...", "params": {...}}' | python -m srdcheck --pipe

Exit codes ARE the verdict: 0 legal / 1 illegal / 2 cannot-adjudicate.
(3 = usage or internal error, never a verdict.)
"""

import json
import pathlib
import sys

from .engine import Engine, validation_refusal
from .schema import issues as schema_issues
from .verdict import VERDICT_OUTPUT_SCHEMA
from .contract import VERDICT_SCHEMA_VERSION

ADAPTERS_DIR = pathlib.Path(__file__).resolve().parent / "adapters"

SCHEMA = {
    "schema_version": VERDICT_SCHEMA_VERSION,
    "input": {
        "type": "object",
        "properties": {
            "type": {"type": "string",
                     "minLength": 1,
                     "description": "query type: 'jurisdiction' or any "
                                    "adapter-defined type (see tool.json)"},
            "params": {"type": "object"},
        },
        "required": ["type"],
        "additionalProperties": False,
    },
    "output": VERDICT_OUTPUT_SCHEMA,
    "exit_codes": {"0": "legal", "1": "illegal", "2": "cannot-adjudicate",
                   "3": "usage or internal error (not a verdict)"},
}


def _engine():
    from .access import default_adapter_paths
    return Engine(default_adapter_paths())


def _emit(verdict):
    print(json.dumps(verdict.as_dict(), indent=2))
    return verdict.exit_code


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 3
    if args[0] == "--schema":
        print(json.dumps(SCHEMA, indent=2))
        return 0
    if args[0] == "capabilities" and len(args) == 1:
        from .access import capabilities
        print(json.dumps(capabilities(), indent=2))
        return 0
    try:
        if args[0] == "--pipe":
            q = json.loads(sys.stdin.read())
            problems = schema_issues(q, SCHEMA["input"])
            if problems:
                return _emit(validation_refusal(problems))
            return _emit(_engine().query(q["type"], q.get("params", {})))
        if args[0] == "conformance" and len(args) == 2:
            from .conformance import check as _cf
            probs = _cf(args[1])
            print(json.dumps({"adapter": args[1], "problems": probs,
                              "ok": not probs}, indent=1))
            return 1 if probs else 0
        if args[0] == "new-adapter" and len(args) == 2:
            from .scaffold import new_adapter
            print(new_adapter(args[1]))
            return 0
        if args[0] == "cite" and len(args) == 2:
            return _emit(_engine().cite(args[1]))
        if args[0] == "jurisdiction" and len(args) == 2:
            return _emit(_engine().jurisdiction(args[1]))
        if args[0] == "query" and len(args) == 3:
            return _emit(_engine().query(args[1], json.loads(args[2])))
        if args[0] == "edition-check" and len(args) >= 2:
            from .access import edition_check
            name = args[1]
            category, current, priors = "creature", "srd-5.2.1", []
            rest = args[2:]
            for i in range(0, len(rest) - 1, 2):
                flag, val = rest[i], rest[i + 1]
                if flag == "--category":
                    category = val
                elif flag == "--current":
                    current = val
                elif flag == "--prior":
                    priors.append(val)
            return _emit(edition_check(name, category, current,
                                       tuple(priors) or ("srd-5.1",)))
    except (ValueError, RecursionError, KeyError) as e:
        print(json.dumps({"error": f"bad input: {e}"}))
        return 3
    print(__doc__)
    return 3


if __name__ == "__main__":
    sys.exit(main())


def script():
    raise SystemExit(main())
