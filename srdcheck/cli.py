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

import hashlib
import json
import pathlib
import sys

from .engine import Engine, validation_refusal
from .schema import issues as schema_issues
from .provenance import ASSERTED_FACTS_SCHEMA, TABLE_DECISION_SCHEMA
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
            "asserted_facts": ASSERTED_FACTS_SCHEMA,
            "table_decision": TABLE_DECISION_SCHEMA,
        },
        "required": ["type"],
        "additionalProperties": False,
    },
    "output": VERDICT_OUTPUT_SCHEMA,
    "table_evaluation": (
        "query/--pipe --table-evaluation emits deterministic self-attested "
        "table.evaluation/1.0; optional --table-context JSON supplies "
        "caller-owned session/entity/correlation references; table and "
        "execution authority remain external"),
    "exit_codes": {"0": "legal", "1": "illegal", "2": "cannot-adjudicate",
                   "3": "usage or internal error (not a verdict)"},
}


def _engine():
    from .access import default_adapter_paths
    return Engine(default_adapter_paths())


def _emit(verdict, table_evaluation=False, query_type=None, params=None,
          table_context=None):
    value = verdict.as_dict()
    if table_evaluation:
        from .table_evaluation import project_table_evaluation
        value = project_table_evaluation(
            value, query_type, params, context=table_context)
        print(json.dumps(value, indent=2))
        return value["exit_code"]
    print(json.dumps(value, indent=2))
    return verdict.exit_code


def _invalid_json_evaluation(query_type, raw, message, table_context=None):
    from .table_evaluation import project_table_evaluation
    from .verdict import cannot_adjudicate

    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    verdict = cannot_adjudicate(
        message, reason_code="invalid-input", missing_inputs=["/params"])
    return project_table_evaluation(
        verdict, query_type or "invalid-query", {"invalid_json_sha256": digest},
        context=table_context)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    metadata = {}
    for flag, key in (("--asserted-facts", "asserted_facts"),
                      ("--table-decision", "table_decision")):
        if args.count(flag) > 1:
            print(json.dumps({"error": f"{flag} may be supplied once"}))
            return 3
        if flag in args:
            index = args.index(flag)
            if index + 1 >= len(args):
                print(json.dumps({"error": f"{flag} requires JSON"}))
                return 3
            try:
                metadata[key] = json.loads(args[index + 1])
            except json.JSONDecodeError:
                print(json.dumps({"error": f"{flag} must be valid JSON"}))
                return 3
            del args[index:index + 2]
    table_evaluation = "--table-evaluation" in args
    if args.count("--table-evaluation") > 1:
        print(json.dumps({"error": "--table-evaluation may be supplied once"}))
        return 3
    if table_evaluation:
        args.remove("--table-evaluation")
    table_context = None
    if args.count("--table-context") > 1:
        print(json.dumps({"error": "--table-context may be supplied once"}))
        return 3
    if "--table-context" in args:
        index = args.index("--table-context")
        if index + 1 >= len(args):
            print(json.dumps({"error": "--table-context requires JSON"}))
            return 3
        raw_context = args[index + 1]
        del args[index:index + 2]
        if not table_evaluation:
            print(json.dumps({
                "error": "--table-context requires --table-evaluation"
            }))
            return 3
        try:
            table_context = json.loads(raw_context)
        except json.JSONDecodeError:
            print(json.dumps({"error": "--table-context must be valid JSON"}))
            return 3
    if not args:
        print(__doc__)
        return 3
    if metadata and args[0] != "query":
        print(json.dumps({
            "error": "--asserted-facts/--table-decision require query"
        }))
        return 3
    if args[0] == "--schema":
        print(json.dumps(SCHEMA, indent=2))
        return 0
    if args[0] == "capabilities" and len(args) == 1:
        from .access import capabilities
        print(json.dumps(capabilities(), indent=2))
        return 0
    if table_evaluation and args[0] not in {"query", "--pipe"}:
        print(json.dumps({
            "error": "--table-evaluation is valid only with query or --pipe"
        }))
        return 3
    try:
        if args[0] == "--pipe":
            raw = sys.stdin.read()
            try:
                q = json.loads(raw)
            except json.JSONDecodeError as exc:
                if table_evaluation:
                    value = _invalid_json_evaluation(
                        "invalid-query", raw, "query JSON is invalid",
                        table_context)
                    print(json.dumps(value, indent=2))
                    return value["exit_code"]
                raise exc
            problems = schema_issues(q, SCHEMA["input"])
            if problems:
                q_type = (q.get("type", "invalid-query")
                          if isinstance(q, dict) else "invalid-query")
                q_params = (q.get("params", {})
                            if isinstance(q, dict) else {})
                return _emit(validation_refusal(problems), table_evaluation,
                             q_type, q_params, table_context)
            return _emit(_engine().query(
                             q["type"], q.get("params", {}),
                             asserted_facts=q.get("asserted_facts"),
                             table_decision=q.get("table_decision")),
                         table_evaluation, q["type"], q.get("params", {}),
                         table_context)
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
            try:
                params = json.loads(args[2])
            except json.JSONDecodeError as exc:
                if table_evaluation:
                    value = _invalid_json_evaluation(
                        args[1], args[2], "params JSON is invalid",
                        table_context)
                    print(json.dumps(value, indent=2))
                    return value["exit_code"]
                raise exc
            return _emit(_engine().query(
                             args[1], params,
                             asserted_facts=metadata.get("asserted_facts"),
                             table_decision=metadata.get("table_decision")),
                         table_evaluation,
                         args[1], params, table_context)
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
