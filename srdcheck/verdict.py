"""Verdict envelope. Content-neutral: no game terms live in this package (T7)."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field

from .contract import VERDICT_SCHEMA_VERSION

LEGAL = 0
ILLEGAL = 1
CANNOT_ADJUDICATE = 2

_NAMES = {LEGAL: "legal", ILLEGAL: "illegal", CANNOT_ADJUDICATE: "cannot-adjudicate"}

COVERAGE_LEVELS = (
    "unknown",
    "registry-only",
    "budget-only",
    "rule-surface-complete",
    "full-context-checkable",
)
_UNKNOWN_SCOPE = "scope metadata is unavailable for this verdict surface"

# Stable agent control-flow vocabulary for exit 2.  ``why`` remains useful to
# humans, but callers must never have to parse it to choose their next step.
REFUSAL_REASON_CODES = (
    "invalid-input",
    "missing-fact",
    "unsupported-content",
    "unmodeled-rule",
    "rules-ambiguous",
    "gm-discretion",
)
REFUSAL_RECOVERABILITY = ("retry", "alternate-path", "authority", "terminal")
REFUSAL_NEXT_ACTIONS = (
    "repair-request",
    "provide-facts",
    "select-adapter",
    "use-other-capability",
    "resolve-table-ruling",
    "stop",
)
REFUSAL_CONTRACT_VERSION = "1.0"
_REFUSAL_CONTRACT = {
    "schema_version": REFUSAL_CONTRACT_VERSION,
    "metadata_location": "data",
    "required_fields": [
        "reason_code",
        "recoverability",
        "missing_inputs",
        "suggested_next_action",
    ],
    "conditional_fields": {
        "required_authority": {
            "when_reason_code": ["rules-ambiguous", "gm-discretion"],
        },
    },
    "vocabularies": {
        "reason_code": list(REFUSAL_REASON_CODES),
        "recoverability": list(REFUSAL_RECOVERABILITY),
        "suggested_next_action": list(REFUSAL_NEXT_ACTIONS),
        "required_authority": ["dm"],
    },
    "reason_mappings": {
        "invalid-input": {
            "recoverability": "retry",
            "suggested_next_action": "repair-request",
        },
        "missing-fact": {
            "recoverability": "retry",
            "suggested_next_action": "provide-facts",
        },
        "unsupported-content": {
            "recoverability": "alternate-path",
            "suggested_next_action": "select-adapter",
        },
        "unmodeled-rule": {
            "recoverability": "alternate-path",
            "suggested_next_action": "use-other-capability",
        },
        "rules-ambiguous": {
            "recoverability": "authority",
            "suggested_next_action": "resolve-table-ruling",
            "required_authority": "dm",
        },
        "gm-discretion": {
            "recoverability": "authority",
            "suggested_next_action": "resolve-table-ruling",
            "required_authority": "dm",
        },
    },
    "allowed_action_overrides": {
        # Known content sent to the wrong capability should be rerouted rather
        # than making the caller look for a different content adapter.
        "unsupported-content": ["use-other-capability"],
    },
    "legacy_fallback": {
        "reason_code": "unmodeled-rule",
        "recoverability": "terminal",
        "missing_inputs": [],
        "suggested_next_action": "stop",
    },
}


def refusal_contract():
    """Return an isolated, JSON-serializable refusal contract description."""
    return deepcopy(_REFUSAL_CONTRACT)

VERDICT_OUTPUT_SCHEMA = {
    "x-srdcheck-schema-version": VERDICT_SCHEMA_VERSION,
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(_NAMES.values())},
        "exit_code": {"type": "integer", "enum": list(_NAMES)},
        "why": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "page": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["section"],
                "additionalProperties": False,
            },
        },
        "rule_ids": {"type": "array", "items": {"type": "string"}},
        "adapter": {"type": "string"},
        "coverage_level": {"type": "string", "enum": list(COVERAGE_LEVELS)},
        "checked_scope": {"type": "array", "items": {"type": "string"}},
        "unchecked_scope": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "data": {"type": "object"},
    },
    "required": ["verdict", "exit_code", "why", "citations", "rule_ids",
                 "adapter", "coverage_level", "checked_scope",
                 "unchecked_scope", "assumptions"],
    "additionalProperties": False,
}


@dataclass
class Citation:
    section: str
    page: int | None = None
    quote: str | None = None

    def as_dict(self):
        d = {"section": self.section}
        if self.page is not None:
            d["page"] = self.page
        if self.quote:
            d["quote"] = self.quote
        return d


@dataclass
class Verdict:
    exit_code: int
    why: str
    citations: list[Citation] = field(default_factory=list)
    adapter: str = ""
    rule_ids: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    coverage_level: str = "unknown"
    checked_scope: list[str] = field(default_factory=list)
    unchecked_scope: list[str] = field(default_factory=lambda: [_UNKNOWN_SCOPE])
    assumptions: list[str] = field(default_factory=list)

    @property
    def verdict(self):
        return _NAMES[self.exit_code]

    def as_dict(self):
        d = {
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "why": self.why,
            "citations": [c.as_dict() for c in self.citations],
            "rule_ids": self.rule_ids,
            "adapter": self.adapter,
            "coverage_level": self.coverage_level,
            "checked_scope": self.checked_scope,
            "unchecked_scope": self.unchecked_scope,
            "assumptions": self.assumptions,
        }
        if self.data:
            d["data"] = self.data
        return d


def legal(why, citations=(), adapter="", rule_ids=(), data=None):
    return Verdict(LEGAL, _scoped_legal_why(why), list(citations), adapter, list(rule_ids),
                   data or {})


def illegal(why, citations=(), adapter="", rule_ids=(), data=None):
    return Verdict(ILLEGAL, why, list(citations), adapter, list(rule_ids),
                   data or {})


def _scoped_legal_why(why):
    suffix = "Legal only within this checked scope."
    text = str(why).rstrip()
    return text if suffix.lower() in text.lower() else f"{text} {suffix}"


def with_scope(result, *, coverage_level, checked_scope, unchecked_scope,
               assumptions=()):
    """Attach one canonical query claim to a verdict without sharing lists."""
    if coverage_level not in COVERAGE_LEVELS:
        raise ValueError(f"unknown coverage level: {coverage_level!r}")
    result.coverage_level = coverage_level
    result.checked_scope = list(checked_scope)
    result.unchecked_scope = list(unchecked_scope)
    result.assumptions = list(assumptions)
    return result


def _refusal_metadata(reason_code, missing_inputs, suggested_next_action):
    """Build and validate the machine-readable recovery contract.

    Calls made before the recovery contract existed omitted all three keyword
    arguments.  Keep those third-party adapters working, but fail closed with a
    terminal response instead of pretending their unclassified refusal is
    recoverable.  New first-party calls are statically guarded elsewhere and
    always provide ``reason_code`` and ``missing_inputs`` explicitly.
    """
    legacy = (reason_code is None and missing_inputs is None
              and suggested_next_action is None)
    if legacy:
        return deepcopy(_REFUSAL_CONTRACT["legacy_fallback"])
    mappings = _REFUSAL_CONTRACT["reason_mappings"]
    if reason_code not in mappings:
        raise ValueError(
            f"reason_code must be one of {REFUSAL_REASON_CODES!r}")
    if missing_inputs is None:
        raise ValueError("missing_inputs must be supplied with reason_code")
    if isinstance(missing_inputs, (str, bytes)):
        raise TypeError("missing_inputs must be an iterable of input paths")
    try:
        normalized = list(missing_inputs)
    except TypeError as exc:
        raise TypeError(
            "missing_inputs must be an iterable of input paths") from exc
    if any(not isinstance(path, str) or not path for path in normalized):
        raise ValueError("missing_inputs must contain non-empty string paths")
    if len(set(normalized)) != len(normalized):
        raise ValueError("missing_inputs must not contain duplicate paths")
    if reason_code == "missing-fact" and not normalized:
        raise ValueError("missing-fact requires at least one missing input path")

    mapping = mappings[reason_code]
    recoverability = mapping["recoverability"]
    canonical_action = mapping["suggested_next_action"]
    authority = mapping.get("required_authority")
    action = (canonical_action if suggested_next_action is None
              else suggested_next_action)
    if action != canonical_action:
        allowed = _REFUSAL_CONTRACT["allowed_action_overrides"].get(
            reason_code, [])
        if action not in allowed:
            raise ValueError(
                f"suggested_next_action {action!r} is not valid for "
                f"reason_code {reason_code!r}")
    metadata = {
        "reason_code": reason_code,
        "recoverability": recoverability,
        "missing_inputs": normalized,
        "suggested_next_action": action,
    }
    if authority is not None:
        metadata["required_authority"] = authority
    return metadata


def cannot_adjudicate(why, citations=(), adapter="", rule_ids=(), data=None, *,
                      reason_code=None, missing_inputs=None,
                      suggested_next_action=None):
    """Return exit 2 with stable, structured recovery instructions.

    ``data`` remains the refusal-metadata location in verdict schema v2.
    Reserved recovery keys are authored by this function and deliberately
    override colliding keys in caller data.
    """
    if data is not None and not isinstance(data, Mapping):
        raise TypeError("data must be a mapping")
    reserved = set(_REFUSAL_CONTRACT["required_fields"])
    reserved.update(_REFUSAL_CONTRACT["conditional_fields"])
    payload = {key: value for key, value in (data or {}).items()
               if key not in reserved}
    payload.update(_refusal_metadata(
        reason_code, missing_inputs, suggested_next_action))
    return Verdict(CANNOT_ADJUDICATE, why, list(citations), adapter,
                   list(rule_ids), payload)
