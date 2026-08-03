"""Issue #28: privacy-safe request tracing without verdict drift."""

import io
import json
import pathlib
import subprocess
import sys

import pytest

from srdcheck.access import default_adapter_paths
from srdcheck.engine import Engine
from srdcheck.mcp import PROTOCOL_VERSION, Server
from srdcheck.observability import (
    OBSERVABILITY_SCHEMA_VERSION, JsonLineSink, configured_sink,
    observability_contract, observe_query, verdict_id,
)
from srdcheck.schema import validate
import srdcheck


ROOT = pathlib.Path(__file__).resolve().parents[1]


def engine():
    return Engine(default_adapter_paths())


def clock(*values):
    readings = iter(values)
    return lambda: next(readings)


def test_observed_query_keeps_verdict_deterministic_and_traces_versions():
    events = []
    first = observe_query(
        engine(), "mage-hand.use", {"kind": "attack"},
        request_id="discord-message-42", sink=events.append,
        clock_ns=clock(1_000_000, 2_500_000),
    )
    second = engine().query("mage-hand.use", {"kind": "attack"})

    assert first.verdict.as_dict() == second.as_dict()
    assert first.trace["request_id"] == "discord-message-42"
    assert first.trace["verdict_id"] == verdict_id(second)
    assert first.trace["duration_ms"] == 1.5
    assert first.trace["engine"]["version"]
    assert {item["name"] for item in first.trace["adapters"]} >= {
        "srd-5.2.1", "toy-tictactoe",
    }
    assert [event["event"] for event in events] == [
        "request.started", "request.completed",
    ]
    schema = observability_contract()["event_schema"]
    for event in events:
        validate(event, schema)


def test_auto_request_and_verdict_ids_are_stable():
    one = observe_query(
        engine(), "jurisdiction", {"name": "Fireball"},
        clock_ns=clock(5, 6),
    )
    two = observe_query(
        engine(), "jurisdiction", {"name": "Fireball"},
        clock_ns=clock(20, 30),
    )
    assert one.trace["request_id"].startswith("auto:sha256:")
    assert one.trace["request_id"] == two.trace["request_id"]
    assert one.trace["verdict_id"] == two.trace["verdict_id"]
    assert one.trace["duration_ms"] != two.trace["duration_ms"]


def test_refusal_reports_machine_class_without_payload_content():
    secret = "campaign-secret-red-dragon-name"
    source_quote = "The hand can't attack"
    events = []
    observed = observe_query(
        engine(), "mage-hand.use", {"kind": "attack", "private": secret},
        sink=events.append, clock_ns=clock(100, 200),
    )
    encoded = json.dumps(events)
    assert observed.trace["event"] == "request.refused"
    assert observed.trace["reason_code"] == "invalid-input"
    assert observed.trace["validation_status"] == "rejected"
    assert secret not in encoded
    assert source_quote not in encoded
    assert "why" not in encoded
    assert "params" not in encoded


def test_errors_are_sanitized_and_re_raised():
    class BrokenEngine:
        adapters = []

        @staticmethod
        def query(*_args, **_kwargs):
            raise RuntimeError("raw private detail")

    events = []
    with pytest.raises(RuntimeError, match="raw private detail"):
        observe_query(
            BrokenEngine(), "example.query", {"private": "do-not-log"},
            sink=events.append, clock_ns=clock(10, 20),
        )
    encoded = json.dumps(events)
    assert events[-1]["event"] == "request.error"
    assert events[-1]["error_type"] == "RuntimeError"
    assert "raw private detail" not in encoded
    assert "do-not-log" not in encoded


def test_broken_sink_never_changes_or_suppresses_a_verdict():
    def broken_sink(_event):
        raise OSError("telemetry destination unavailable")

    observed = observe_query(
        engine(), "jurisdiction", {"name": "Fireball"},
        sink=broken_sink, clock_ns=clock(10, 20),
    )
    direct = engine().query("jurisdiction", {"name": "Fireball"})
    assert observed.verdict.as_dict() == direct.as_dict()


@pytest.mark.parametrize("request_id", ["", "\n", "x" * 245, 7])
def test_caller_request_id_is_bounded_and_printable(request_id):
    with pytest.raises(ValueError, match="request_id"):
        observe_query(engine(), "jurisdiction", {"name": "Fireball"},
                      request_id=request_id)


def test_json_line_logging_is_opt_in_and_canonical():
    assert configured_sink(environ={}) is None
    stream = io.StringIO()
    sink = configured_sink(stream=stream, environ={"SRDCHECK_TRACE": "stderr"})
    assert isinstance(sink, JsonLineSink)
    observe_query(engine(), "jurisdiction", {"name": "Fireball"},
                  request_id="request-7", sink=sink,
                  clock_ns=clock(1, 2))
    lines = stream.getvalue().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["schema_version"] == \
        OBSERVABILITY_SCHEMA_VERSION


def test_unknown_trace_configuration_fails_closed():
    with pytest.raises(ValueError, match="SRDCHECK_TRACE"):
        configured_sink(environ={"SRDCHECK_TRACE": "raw-payloads"})


def test_capabilities_publish_the_observability_contract():
    capabilities = srdcheck.capabilities()
    assert capabilities["machine_contracts"][
        "observability_contract_version"] == OBSERVABILITY_SCHEMA_VERSION
    assert capabilities["observability_contract"] == observability_contract()


def test_cli_trace_is_stderr_only_and_preserves_stdout_verdict():
    secret = "private-campaign-token"
    result = subprocess.run([
        sys.executable, "-m", "srdcheck", "query", "mage-hand.use",
        json.dumps({"kind": "attack", "private": secret}),
        "--trace", "--request-id", "discord-55",
    ], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    verdict = json.loads(result.stdout)
    assert verdict["data"]["reason_code"] == "invalid-input"
    events = [json.loads(line) for line in result.stderr.splitlines()]
    assert [event["event"] for event in events] == [
        "request.started", "request.refused",
    ]
    assert events[-1]["request_id"] == "discord-55"
    assert secret not in result.stderr


def test_mcp_trace_uses_caller_request_id_without_changing_result():
    events = []
    server = Server(event_sink=events.append, clock_ns=clock(10, 20))
    server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "trace-test", "version": "1.0"},
        },
    })
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = server.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "jurisdiction",
            "arguments": {"name": "Fireball", "request_id": "discord-56"},
        },
    })
    assert response["result"]["structuredContent"]["exit_code"] == 0
    assert events[-1]["request_id"] == "discord-56"
    assert events[-1]["event"] == "request.completed"
    assert "request_id" not in response["result"]["structuredContent"]
