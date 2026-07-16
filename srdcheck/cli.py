"""srdcheck CLI.

  python -m srdcheck jurisdiction "<name>"
  python -m srdcheck query <query-type> '<params-json>'
  python -m srdcheck --schema
  echo '{"type": "...", "params": {...}}' | python -m srdcheck --pipe

Exit codes ARE the verdict: 0 legal / 1 illegal / 2 cannot-adjudicate.
(3 = usage or internal error, never a verdict.)
"""

import json
import pathlib
import sys

from .engine import Engine

ADAPTERS_DIR = pathlib.Path(__file__).resolve().parent / "adapters"

SCHEMA = {
    "input": {
        "type": "object",
        "properties": {
            "type": {"type": "string",
                     "description": "query type: 'jurisdiction' or any "
                                    "adapter-defined type (see tool.json)"},
            "params": {"type": "object"},
        },
        "required": ["type"],
    },
    "output": {
        "type": "object",
        "properties": {
            "verdict": {"enum": ["legal", "illegal", "cannot-adjudicate"]},
            "exit_code": {"enum": [0, 1, 2]},
            "why": {"type": "string"},
            "citations": {"type": "array"},
            "rule_ids": {"type": "array"},
            "adapter": {"type": "string"},
        },
    },
    "exit_codes": {"0": "legal", "1": "illegal", "2": "cannot-adjudicate",
                   "3": "usage or internal error (not a verdict)"},
}


def _engine():
    paths = sorted(p for p in ADAPTERS_DIR.iterdir() if (p / "manifest.json").exists())
    return Engine(paths)


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
    try:
        if args[0] == "--pipe":
            q = json.loads(sys.stdin.read())
            return _emit(_engine().query(q["type"], q.get("params", {})))
        if args[0] == "jurisdiction" and len(args) == 2:
            return _emit(_engine().jurisdiction(args[1]))
        if args[0] == "query" and len(args) == 3:
            return _emit(_engine().query(args[1], json.loads(args[2])))
    except (json.JSONDecodeError, KeyError) as e:
        print(json.dumps({"error": f"bad input: {e}"}))
        return 3
    print(__doc__)
    return 3


if __name__ == "__main__":
    sys.exit(main())


def script():
    raise SystemExit(main())
