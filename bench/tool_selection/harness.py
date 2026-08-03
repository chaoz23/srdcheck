#!/usr/bin/env python3
"""Preregistered SRDCheck MCP first-call selection harness (issue #32)."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES_PATH = pathlib.Path(__file__).with_name("cases.jsonl")

SYSTEM_PROMPT = """You are the DM running a D&D game for human players over Discord.
Use SRDCheck before narrating the mechanical ruling. Select exactly one first
tool call from the catalog. Do not answer the rules question yourself. Return
ONLY one JSON object in this form:
{"tool": "tool_name" or null, "arguments": {}}
Use null only when the catalog has no suitable tool. Preserve every supplied
mechanical fact in the tool arguments."""


def load_cases(path=CASES_PATH):
    return [json.loads(line) for line in pathlib.Path(path).read_text().splitlines()
            if line.strip()]


def case_digest(path=CASES_PATH):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def engine_and_specialized_tools():
    from srdcheck.access import default_adapter_paths
    from srdcheck.engine import Engine
    from srdcheck.mcp import build_tools
    engine = Engine(default_adapter_paths())
    tools, _ = build_tools(engine)
    return engine, tools


def compact_tools(engine):
    query_types = sorted({query for adapter in engine.adapters
                          for query in adapter.query_types})
    enumerators = sorted(query for query in query_types
                         if query.endswith(".options"))
    query_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["query_type", "params"],
        "properties": {
            "query_type": {"type": "string", "enum": query_types},
            "params": {"type": "object"},
        },
    }
    enumerate_schema = json.loads(json.dumps(query_schema))
    enumerate_schema["properties"]["query_type"]["enum"] = enumerators
    return [
        {
            "name": "capabilities",
            "description": "Discover supported rulesets, query types, versions, and scope.",
            "inputSchema": {"type": "object", "additionalProperties": False},
        },
        {
            "name": "evaluate",
            "description": "Evaluate one named rules query with its supplied facts.",
            "inputSchema": query_schema,
        },
        {
            "name": "enumerate",
            "description": "Enumerate legal options through a supported options query.",
            "inputSchema": enumerate_schema,
        },
        {
            "name": "explain",
            "description": "Return the verbatim SRD source passage for a heading.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {"name": {"type": "string", "minLength": 1}},
            },
        },
    ]


def catalog(arm):
    engine, specialized = engine_and_specialized_tools()
    if arm == "specialized":
        return engine, specialized
    if arm == "compact":
        return engine, compact_tools(engine)
    raise ValueError(f"unknown arm: {arm}")


def expected_call(case, arm):
    operation = case["operation"]
    if arm == "specialized":
        if case["lane"] == "protocol-only":
            return {"tool": None, "arguments": {}}
        return {
            "tool": case["query_type"].replace(".", "_").replace("-", "_"),
            "arguments": case["params"],
        }
    if operation in ("evaluate", "enumerate"):
        arguments = {"query_type": case["query_type"], "params": case["params"]}
    elif operation == "explain":
        arguments = case["params"]
    else:
        arguments = {}
    return {"tool": operation, "arguments": arguments}


def render_prompt(case, arm, tools):
    return (SYSTEM_PROMPT + "\n\nArm: " + arm + "\nTool catalog:\n" +
            json.dumps(tools, separators=(",", ":"), sort_keys=True) +
            "\n\nTable situation:\n" + case["prompt"])


def parse_call(text):
    start = text.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or set(value) != {"tool", "arguments"}:
        return None
    if value["tool"] is not None and not isinstance(value["tool"], str):
        return None
    if not isinstance(value["arguments"], dict):
        return None
    return value


def execute(engine, case, arm, call):
    if call["tool"] is None:
        return None
    if arm == "specialized":
        query_type = case["query_type"]
        result = engine.query(query_type, call["arguments"]).as_dict()
    elif call["tool"] in ("evaluate", "enumerate"):
        args = call["arguments"]
        if not isinstance(args.get("query_type"), str) or not isinstance(
                args.get("params"), dict):
            return None
        result = engine.query(args["query_type"], args["params"]).as_dict()
    elif call["tool"] == "explain":
        if not isinstance(call["arguments"].get("name"), str):
            return None
        result = engine.cite(call["arguments"]["name"]).as_dict()
    elif call["tool"] == "capabilities":
        if call["arguments"]:
            return None
        return {"capabilities": True}
    else:
        return None
    return result


def assess(engine, case, arm, raw_answer):
    call = parse_call(raw_answer)
    if call is None:
        return {"answer": None, "broken": True, "selection_success": False,
                "argument_success": False, "execution_success": False,
                "first_call_success": False}
    expected = expected_call(case, arm)
    selection = call["tool"] == expected["tool"]
    arguments = selection and call["arguments"] == expected["arguments"]
    result = execute(engine, case, arm, call) if selection else None
    if expected["tool"] is None:
        execution = call["tool"] is None
    elif case.get("expected") is None:
        execution = result is not None or (expected["tool"] is None and
                                           call["tool"] is None)
    else:
        execution = (isinstance(result, dict) and
                     result.get("verdict") == case["expected"]["verdict"] and
                     result.get("exit_code") == case["expected"]["exit_code"])
    return {"answer": call, "broken": False,
            "selection_success": selection,
            "argument_success": arguments,
            "execution_success": execution,
            "first_call_success": selection and arguments and execution}


def gemini_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    secret = pathlib.Path.home() / ".openclaw/secrets/gemini.env"
    match = re.search(r"GEMINI_API_KEY=(\S+)", secret.read_text())
    if not match:
        raise RuntimeError("GEMINI_API_KEY is unavailable")
    return match.group(1)


def make_driver(spec):
    kind, separator, name = spec.partition(":")
    if not separator or not name:
        raise ValueError("subject must be gemini:<model>, ollama:<model>, or cmd:<command>")
    if kind == "gemini":
        def call(prompt):
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 300},
            }).encode()
            request = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models/" +
                name + ":generateContent", data=body,
                headers={"Content-Type": "application/json",
                         "x-goog-api-key": gemini_key()})
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.load(response)
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        return call
    if kind == "ollama":
        def call(prompt):
            body = json.dumps({"model": name, "stream": False, "think": False,
                               "messages": [{"role": "user", "content": prompt}],
                               "options": {"num_predict": 300, "temperature": 0}}).encode()
            request = urllib.request.Request(
                "http://127.0.0.1:11434/api/chat", data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.load(response)["message"]["content"]
        return call
    if kind == "cmd":
        command = shlex.split(name)

        def call(prompt):
            completed = subprocess.run(command, input=prompt, text=True,
                                       capture_output=True, timeout=600,
                                       check=False)
            return completed.stdout
        return call
    raise ValueError(f"unknown subject kind: {kind}")


def current_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()


def run(args):
    cases = load_cases(args.cases)
    engine, tools = catalog(args.arm)
    serialized_catalog = json.dumps(tools, separators=(",", ":"), sort_keys=True)
    driver = make_driver(args.subject)
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if output.exists():
        done = {(record["id"], record["arm"], record["subject"],
                 record["replicate"])
                for record in (json.loads(line) for line in output.read_text().splitlines())}
    for replicate in range(1, args.replicates + 1):
        for case in cases:
            key = (case["id"], args.arm, args.subject, replicate)
            if key in done:
                continue
            try:
                raw = driver(render_prompt(case, args.arm, tools))
                scored = assess(engine, case, args.arm, raw)
            except Exception as exc:  # noqa: BLE001 - recorded benchmark failure
                raw = ""
                scored = {"answer": None, "broken": True,
                          "selection_success": False, "argument_success": False,
                          "execution_success": False, "first_call_success": False,
                          "driver_error": type(exc).__name__ + ": " + str(exc)[:200]}
            record = {
                "id": case["id"], "lane": case["lane"], "arm": args.arm,
                "subject": args.subject, "cohort": args.cohort,
                "replicate": replicate, "commit": current_commit(),
                "run_date": datetime.now(timezone.utc).isoformat(),
                "case_digest": case_digest(args.cases),
                "catalog_tools": len(tools),
                "catalog_bytes": len(serialized_catalog.encode("utf-8")),
                **scored,
            }
            with output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
            print(case["id"], args.arm, replicate,
                  "PASS" if record["first_call_success"] else "FAIL", flush=True)


def validate_cases(path):
    cases = load_cases(path)
    engine, _ = engine_and_specialized_tools()
    errors = []
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("case ids must be unique")
    for case in cases:
        prefix = case.get("id", "<unknown>")
        if case.get("lane") not in ("common", "protocol-only"):
            errors.append(prefix + ": invalid lane")
        if case.get("operation") not in ("capabilities", "evaluate", "enumerate",
                                          "explain"):
            errors.append(prefix + ": invalid operation")
            continue
        if case["operation"] in ("evaluate", "enumerate"):
            result = engine.query(case.get("query_type"), case.get("params", {})).as_dict()
        elif case["operation"] == "explain":
            result = engine.cite(case.get("params", {}).get("name", "")).as_dict()
        else:
            result = None
        if result is not None and case.get("expected") != {
                "verdict": result["verdict"], "exit_code": result["exit_code"]}:
            errors.append(prefix + ": expected result does not match engine")
    return errors


def summarize(records):
    groups = defaultdict(lambda: {metric: 0 for metric in (
        "n", "selection_success", "argument_success", "execution_success",
        "first_call_success", "broken")})
    for record in records:
        key = (record["cohort"], record["subject"], record["arm"],
               record["lane"], record["replicate"])
        group = groups[key]
        group["n"] += 1
        for metric in group:
            if metric != "n":
                group[metric] += int(bool(record.get(metric)))
        group["catalog_tools"] = record["catalog_tools"]
        group["catalog_bytes"] = record["catalog_bytes"]
    return {"|".join(map(str, key)): value for key, value in sorted(groups.items())}


def load_results(paths):
    return [json.loads(line) for path in paths
            for line in pathlib.Path(path).read_text().splitlines() if line.strip()]


def validate_results(paths):
    cases = {case["id"]: case for case in load_cases()}
    digest = case_digest()
    errors = []
    for path in paths:
        records = load_results([path])
        prefix = pathlib.Path(path).name
        keys = [(record.get("id"), record.get("replicate")) for record in records]
        expected_keys = {(case_id, replicate) for case_id in cases
                         for replicate in (1, 2)}
        if set(keys) != expected_keys or len(keys) != len(expected_keys):
            errors.append(prefix + ": must contain each case exactly once per replicate")
        identities = {(record.get("subject"), record.get("cohort"),
                       record.get("arm")) for record in records}
        if len(identities) != 1:
            errors.append(prefix + ": must contain one subject/cohort/arm identity")
        for record in records:
            location = prefix + ":" + str(record.get("id")) + ":r" + str(
                record.get("replicate"))
            case = cases.get(record.get("id"))
            if case is None:
                errors.append(location + ": unknown case")
                continue
            if record.get("case_digest") != digest:
                errors.append(location + ": stale case digest")
            if record.get("lane") != case["lane"]:
                errors.append(location + ": stale lane")
            if record.get("arm") not in ("specialized", "compact"):
                errors.append(location + ": invalid arm")
                continue
            _, tools = catalog(record["arm"])
            encoded = json.dumps(tools, separators=(",", ":"), sort_keys=True).encode()
            if (record.get("catalog_tools"), record.get("catalog_bytes")) != (
                    len(tools), len(encoded)):
                errors.append(location + ": stale catalog identity")
            if not isinstance(record.get("commit"), str) or len(record["commit"]) != 40:
                errors.append(location + ": missing exact commit")
            if not isinstance(record.get("run_date"), str):
                errors.append(location + ": missing run date")
            answer = record.get("answer")
            if answer is None:
                recomputed = {"broken": True, "selection_success": False,
                              "argument_success": False, "execution_success": False,
                              "first_call_success": False}
            else:
                engine, _ = catalog(record["arm"])
                recomputed = assess(engine, case, record["arm"], json.dumps(answer))
            for metric in ("broken", "selection_success", "argument_success",
                           "execution_success", "first_call_success"):
                if record.get(metric) != recomputed[metric]:
                    errors.append(location + ": stale score " + metric)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate-set")
    validate_parser.add_argument("--cases", default=str(CASES_PATH))
    catalog_parser = subparsers.add_parser("catalog")
    catalog_parser.add_argument("--arm", choices=("specialized", "compact"),
                                required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--arm", choices=("specialized", "compact"), required=True)
    run_parser.add_argument("--subject", required=True)
    run_parser.add_argument("--cohort", choices=("frontier", "mid-tier", "local"),
                            required=True)
    run_parser.add_argument("--replicates", type=int, default=2)
    run_parser.add_argument("--cases", default=str(CASES_PATH))
    run_parser.add_argument("--output", required=True)
    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("results", nargs="+")
    result_parser = subparsers.add_parser("validate-results")
    result_parser.add_argument("results", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "validate-set":
        errors = validate_cases(args.cases)
        if errors:
            for error in errors:
                print(error)
            return 1
        print(f"valid: {len(load_cases(args.cases))} cases; sha256={case_digest(args.cases)}")
        return 0
    if args.command == "catalog":
        _, tools = catalog(args.arm)
        encoded = json.dumps(tools, separators=(",", ":"), sort_keys=True).encode()
        print(json.dumps({"arm": args.arm, "tools": len(tools),
                          "catalog_bytes": len(encoded)}, indent=2))
        return 0
    if args.command == "run":
        run(args)
        return 0
    if args.command == "validate-results":
        errors = validate_results(args.results)
        if errors:
            for error in errors:
                print(error)
            return 1
        print(f"valid: {len(load_results(args.results))} result records")
        return 0
    records = load_results(args.results)
    print(json.dumps(summarize(records), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
