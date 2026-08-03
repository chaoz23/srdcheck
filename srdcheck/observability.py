"""Privacy-safe, out-of-band query observability.

Verdicts stay deterministic. Timing and occurrence metadata travel only in
this separate event contract, never in the verdict envelope.
"""

import hashlib
import json
import os
import sys
import time
from copy import deepcopy
from dataclasses import dataclass

from . import __version__
from .contract import OBSERVABILITY_SCHEMA_VERSION


REQUEST_ID_MAX_LENGTH = 244

OBSERVABILITY_EVENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "event", "request_id", "query_type", "engine",
        "adapters",
    ],
    "properties": {
        "schema_version": {
            "type": "string", "enum": [OBSERVABILITY_SCHEMA_VERSION],
        },
        "event": {
            "type": "string",
            "enum": [
                "request.started", "request.completed", "request.refused",
                "request.error",
            ],
        },
        "request_id": {
            "type": "string", "minLength": 1,
            "maxLength": REQUEST_ID_MAX_LENGTH,
        },
        "query_type": {"type": "string", "minLength": 1},
        "engine": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
            },
        },
        "adapters": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "version", "data_version",
                             "rules_version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"},
                    "data_version": {"type": "string"},
                    "rules_version": {"type": "string"},
                },
            },
        },
        "verdict_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "outcome": {
            "type": "string",
            "enum": ["legal", "illegal", "cannot-adjudicate"],
        },
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
        "reason_code": {"type": "string"},
        "validation_status": {
            "type": "string", "enum": ["accepted", "rejected"],
        },
        "duration_ms": {"type": "number", "minimum": 0},
        "error_type": {"type": "string", "minLength": 1},
    },
}


def observability_contract():
    """Return an isolated description suitable for capability discovery."""
    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "delivery": "out-of-band",
        "default": "disabled",
        "payload_policy": "metadata-only",
        "event_schema": deepcopy(OBSERVABILITY_EVENT_SCHEMA),
    }


def _canonical_hash(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _request_id(query_type, params, supplied):
    if supplied is not None:
        if (not isinstance(supplied, str)
                or not 1 <= len(supplied) <= REQUEST_ID_MAX_LENGTH
                or not supplied.isprintable()):
            raise ValueError(
                "request_id must be a printable 1..244 character string")
        return supplied
    try:
        digest = _canonical_hash({"query_type": query_type, "params": params})
    except (TypeError, ValueError, RecursionError):
        digest = _canonical_hash({
            "query_type_type": type(query_type).__name__,
            "params_type": type(params).__name__,
        })
    return "auto:" + digest


def verdict_id(verdict):
    """Return the deterministic identity of one semantic verdict payload."""
    value = verdict.as_dict() if hasattr(verdict, "as_dict") else verdict
    return _canonical_hash(value)


def _adapters(engine):
    return [
        {
            "name": str(adapter.manifest.get("name", "")),
            "version": str(adapter.manifest.get("version", "")),
            "data_version": str(adapter.data_version),
            "rules_version": str(adapter.rules_version),
        }
        for adapter in engine.adapters
    ]


def _base_event(engine, query_type, request_id):
    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "request_id": request_id,
        "query_type": (query_type if isinstance(query_type, str)
                       and query_type else "invalid-query"),
        "engine": {"name": "srdcheck", "version": __version__},
        "adapters": _adapters(engine),
    }


def _send(sink, event):
    if sink is not None:
        # Observability is strictly out-of-band: a closed stream or broken
        # caller exporter must never change, suppress, or replace a verdict.
        try:
            sink(deepcopy(event))
        except Exception:  # noqa: BLE001 — telemetry is best-effort by design
            pass


@dataclass(frozen=True)
class ObservedResult:
    verdict: object
    trace: dict


def observe_query(engine, query_type, params, *, request_id=None, sink=None,
                  clock_ns=time.perf_counter_ns, **query_options):
    """Run one query while emitting metadata-only lifecycle events.

    The returned verdict is the engine's original object. The trace summary is
    occurrence metadata and is deliberately excluded from ``Verdict.as_dict``.
    """
    rid = _request_id(query_type, params, request_id)
    base = _base_event(engine, query_type, rid)
    started = {**base, "event": "request.started"}
    _send(sink, started)
    began = clock_ns()
    try:
        verdict = engine.query(query_type, params, **query_options)
    except Exception as exc:
        elapsed = max(0, clock_ns() - began) / 1_000_000
        failed = {
            **base, "event": "request.error", "duration_ms": elapsed,
            "error_type": type(exc).__name__,
        }
        _send(sink, failed)
        raise
    elapsed = max(0, clock_ns() - began) / 1_000_000
    payload = verdict.as_dict()
    refused = verdict.exit_code == 2
    completed = {
        **base,
        "event": "request.refused" if refused else "request.completed",
        "verdict_id": verdict_id(payload),
        "outcome": verdict.verdict,
        "exit_code": verdict.exit_code,
        "validation_status": (
            "rejected" if (payload.get("data") or {}).get("reason_code")
            == "invalid-input" else "accepted"),
        "duration_ms": elapsed,
    }
    reason = (payload.get("data") or {}).get("reason_code")
    if refused and reason:
        completed["reason_code"] = reason
    _send(sink, completed)
    return ObservedResult(verdict=verdict, trace=completed)


class JsonLineSink:
    """Write one canonical metadata event per line to a caller-owned stream."""

    def __init__(self, stream):
        self.stream = stream

    def __call__(self, event):
        self.stream.write(json.dumps(
            event, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")) + "\n")
        self.stream.flush()


def configured_sink(stream=None, environ=None):
    """Return the opt-in stderr sink selected by ``SRDCHECK_TRACE``."""
    value = (os.environ if environ is None else environ).get(
        "SRDCHECK_TRACE", "off").strip().lower()
    if value in {"", "0", "false", "off"}:
        return None
    if value == "stderr":
        return JsonLineSink(stream or sys.stderr)
    raise ValueError("SRDCHECK_TRACE must be 'off' or 'stderr'")
