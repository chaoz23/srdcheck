"""Shared vocabulary for the srd-5.2.1 handlers: citation shaping, param
reading, the modeled-condition model, and the fact-dependency refusals.

Owns no query. Every other module may import from here; this module imports
from none of them.
"""
import json

from srdcheck import verdict as v
from srdcheck.schema import (ValidationIssue)

def _cite(atom):
    c = atom["citation"]
    return v.Citation(f"SRD 5.2.1 p.{c['page']} '{c['section']}'",
                      c["page"], c.get("quote"))


def event_int(p, key):
    """Read an integer param, or None if absent. Keeps None distinct from 0
    (a declared d20 of 0 is invalid; an absent one means 'DC only')."""
    val = p.get(key)
    return int(val) if val is not None else None


# Turn economy. Conditions whose action-economy effects this adapter version
# models. Any other condition yields exit 2 rather than a silently wrong
# verdict (T1/T8) — several unmodeled conditions (Stunned, Paralyzed, ...)
# include Incapacitated, so ignoring them would corrupt verdicts.
# completeness pass: every SRD condition with a codified turn-economy effect (or
# none) is handled, so none is silently refused as merely unbuilt. Petrified and
# Unconscious DEFINITIONALLY embed Incapacitated (and Unconscious embeds Prone);
# Frightened/Poisoned/Charmed/Deafened impose no economy restriction this surface
# can check (Frightened's can't-approach is direction geometry, deferred by T6).
# Every SRD condition is modeled on the turn-economy surface. Exhaustion needs
# its level (a graduated Speed reduction), so it's modeled only when the caller
# supplies exhaustion_level; the name alone gets a specific reasoned refusal.
_MODELED_CONDITIONS = {"grappled", "prone", "incapacitated", "frightened",
                       "poisoned", "charmed", "deafened", "petrified",
                       "unconscious", "blinded", "invisible", "restrained",
                       "stunned", "paralyzed", "exhaustion"}
# source condition -> (implied conditions it embeds, the citing atom for the embed)
_CONDITION_EMBEDS = {
    "stunned": (["incapacitated"], "condition.stunned.incapacitated"),
    "paralyzed": (["incapacitated"], "condition.paralyzed.incapacitated"),
    "petrified": (["incapacitated"], "condition.petrified.incapacitated"),
    "unconscious": (["incapacitated", "prone"], "condition.unconscious.inert"),
}
# conditions that set Speed 0 -> the atom that says so
_SPEED_ZERO = {"grappled": "condition.grappled.speed-zero",
               "restrained": "condition.restrained.speed-zero",
               "paralyzed": "condition.paralyzed.speed-zero",
               "petrified": "condition.petrified.speed-zero",
               "unconscious": "condition.unconscious.speed-zero"}
def _expand_conditions(lower_conds):
    """Expand definitional embeds (Petrified/Unconscious carry Incapacitated,
    etc.). Returns (expanded_set, embed_atom_ids to co-cite when the embedded
    effect fires) so a Petrified 'can't act' verdict cites *why* it's inactive."""
    expanded, embeds = set(lower_conds), []
    for c, (implied, atom_id) in _CONDITION_EMBEDS.items():
        if c in lower_conds:
            expanded.update(implied)
            embeds.append(atom_id)
    return expanded, embeds


def _condition_dependency_contract(adapter):
    """Load the adapter-owned, machine-readable condition/fact contract."""
    cached = getattr(adapter, "_condition_dependency_contract", None)
    if cached is None:
        path = adapter.root / "condition_dependencies.json"
        cached = json.loads(path.read_text(encoding="utf-8"))
        adapter._condition_dependency_contract = cached
    return cached


def _effect_required_facts(adapter, surface, effect):
    return _condition_dependency_contract(adapter)["surfaces"][surface][
        "effects"][effect]["required_facts"]


def _query_required_facts(adapter, surface, dependency):
    return _condition_dependency_contract(adapter)["surfaces"][surface][
        "query_dependencies"][dependency]["required_facts"]


def _path_present(payload, path):
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _missing_fact_refusal(adapter, paths):
    """Return one deterministic missing-fact verdict for exact request paths."""
    from srdcheck.engine import validation_refusal
    unique = list(dict.fromkeys(paths))
    return validation_refusal([
        ValidationIssue(f"$.{path}", "required", "required field is missing")
        for path in unique
    ], adapter.id)


def _condition_category_gate(adapter, supplied, modeled, surface):
    """Shared condition-name/category/model gate for roll surfaces."""
    normalized = set()
    for raw in supplied:
        if not isinstance(raw, str) or not raw.strip():
            return None, v.cannot_adjudicate(
                "Condition names must be non-empty strings.",
                adapter=adapter.id, reason_code="invalid-input",
                missing_inputs=())
        name = raw.strip()
        categories = adapter.lookup_entity(name) or []
        if not categories:
            return None, v.cannot_adjudicate(
                f"'{name}' is not a condition known to this ruleset.",
                adapter=adapter.id, reason_code="unsupported-content",
                missing_inputs=())
        if "condition" not in categories:
            return None, v.cannot_adjudicate(
                f"'{name}' is known content, but is not a condition.",
                adapter=adapter.id, reason_code="invalid-input",
                missing_inputs=())
        key = name.casefold()
        if key not in modeled:
            return None, v.cannot_adjudicate(
                f"'{name}' is a real condition, but its {surface} effects are "
                "not modeled in this adapter version.", adapter=adapter.id,
                reason_code="unmodeled-rule", missing_inputs=())
        normalized.add(key)
    return normalized, None
