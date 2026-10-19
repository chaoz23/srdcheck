"""Content lookups and the Mage Hand adjudication.

Owns: spell.facts, feature.uses, mage-hand.use
"""
import json

from srdcheck import verdict as v
from srdcheck.schema import (issues as schema_issues, normalize_integers)
from .common import _cite

def mage_hand_use(adapter, p):
    """p: {kind, weight_lb?, distance_ft?} — one proposed use of the hand."""
    schema = adapter.query_meta["mage-hand.use"]["inputSchema"]
    problems = schema_issues(p, schema)
    if problems:
        from srdcheck.engine import validation_refusal
        return validation_refusal(problems, adapter.id)
    p = normalize_integers(p, schema)
    a = adapter.atoms
    aid = adapter.id
    kind = p["kind"].strip()
    if not kind:
        return v.cannot_adjudicate(
            "Mage Hand use kind must not be blank.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    if p.get("weight_lb", 0) < 0 or p.get("distance_ft", 0) < 0:
        return v.cannot_adjudicate(
            "Negative weight or distance is not a valid input; cannot "
            "adjudicate.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())

    leash = a["mage-hand.range-leash"]
    if p.get("distance_ft", 0) > leash["params"]["max"]:
        return v.illegal(
            f"The hand vanishes beyond {leash['params']['max']} feet; the "
            f"target is {p['distance_ft']} feet away.",
            [_cite(leash)], aid, [leash["id"]])

    for atom_id in ("mage-hand.cant-attack", "mage-hand.cant-activate-magic-items"):
        atom = a[atom_id]
        if kind == atom["params"]["use"]:
            return v.illegal(atom["citation"]["quote"] + ".",
                             [_cite(atom)], aid, [atom_id])

    carry = a["mage-hand.carry-limit"]
    if p.get("weight_lb", 0) > carry["params"]["max"]:
        return v.illegal(
            f"The hand can't carry more than {carry['params']['max']} pounds; "
            f"the object weighs {p['weight_lb']} pounds.",
            [_cite(carry)], aid, [carry["id"]])

    grants = a["mage-hand.granted-uses"]
    if kind in grants["params"]["uses"]:
        required = ["distance_ft"]
        if kind in {"manipulate_object", "stow_retrieve_open", "pour_vial"}:
            required.append("weight_lb")
        missing = [name for name in required if name not in p]
        if missing:
            return v.cannot_adjudicate(
                "The proposed granted use still depends on missing weight or "
                "distance facts; provide only the listed facts before "
                "adjudication.", adapter=aid,
                reason_code="missing-fact", missing_inputs=missing)
        why = [f"granted use: '{grants['params']['uses'][kind]}'"]
        if "weight_lb" in p:
            why.append(f"{p['weight_lb']} lb is within the "
                       f"{carry['params']['max']} lb limit")
        if "distance_ft" in p:
            why.append(f"{p['distance_ft']} ft is within the "
                       f"{leash['params']['max']} ft range")
        return v.legal("; ".join(why) + ".", [_cite(grants)], aid, [grants["id"]])

    return v.cannot_adjudicate(
        "The spell text neither grants nor forbids this use. Whether "
        "'manipulate an object' extends to it — and any check required — "
        "must be resolved as a table ruling by the authorized DM, including "
        "the calling agent when it is the DM.",
        [_cite(grants)], aid, [grants["id"]],
        reason_code="gm-discretion", missing_inputs=())



_SPELL_FACTS = None


def _spell_facts(adapter):
    global _SPELL_FACTS
    if _SPELL_FACTS is None:
        _SPELL_FACTS = json.load(open(adapter.root / "spell_facts.json"))
    return _SPELL_FACTS


def spell_facts(adapter, p):
    """Machine-readable spell facts (casting time, range, components,
    duration, concentration), census-anchored against the spell registry.
    With caller-supplied `cast_at`, returns expires_at as pure arithmetic on
    the caller's own clock - srdcheck holds no state and no clock. Origin:
    a 10-minute ward narrated as active for ~70 minutes (2026-07-27)."""
    aid = adapter.id
    if "name" not in p:
        return v.cannot_adjudicate(
            "Provide a spell name.", adapter=aid,
            reason_code="missing-fact", missing_inputs=("name",))
    name = (p["name"] or "").strip().lower()
    if not name:
        return v.cannot_adjudicate(
            "Spell name must not be blank.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    facts = _spell_facts(adapter)
    if name not in facts:
        categories = adapter.lookup_entity(name) or []
        if categories and "spell" not in categories:
            return v.cannot_adjudicate(
                f"'{p.get('name')}' is registered SRD 5.2.1 content, but is "
                "not a spell.", adapter=aid, reason_code="unsupported-content",
                missing_inputs=(),
                suggested_next_action="use-other-capability")
        return v.cannot_adjudicate(
            f"'{p.get('name')}' is not a registered SRD 5.2.1 spell name.",
            adapter=aid, reason_code="unsupported-content",
            missing_inputs=())
    f = dict(facts[name])
    pg = f.pop("page")
    data = {"facts": f}
    why = (f"{p.get('name')}: casting time {f['casting_time']}; range "
           f"{f['range']}; components {f['components']}; duration "
           f"{f['duration']}" + ("; CONCENTRATION" if f["concentration"] else ""))
    cast_at = p.get("cast_at")
    if cast_at is not None:
        import re as _re
        m = _re.search(r"(\d+)\s*(round|minute|hour|day)", f["duration"].lower())
        if m:
            mult = {"round": 6, "minute": 60, "hour": 3600, "day": 86400}[m.group(2)]
            data["expires_at"] = float(cast_at) + int(m.group(1)) * mult
            data["duration_seconds"] = int(m.group(1)) * mult
            why += f"; expires_at {data['expires_at']} on the caller's clock"
        else:
            data["expires_at"] = None
            why += "; duration is not a fixed interval - caller adjudicates expiry"
    return v.legal(why, [v.Citation(f"SRD 5.2.1 p.{pg}", pg, None)], aid,
                   ["spell.facts"], data=data)


_FEATURE_USES = {
    "divine-sense": {"formula": "1 + Charisma modifier",
                     "blanks": ["charisma_modifier"],
                     "fn": lambda p: 1 + int(p.get("charisma_modifier", 0)),
                     "page": 87},
    "lay-on-hands": {"formula": "5 x paladin level (hit point pool)",
                     "blanks": ["paladin_level"],
                     "fn": lambda p: 5 * int(p.get("paladin_level", 0)),
                     "page": 87},
}


def feature_uses(adapter, p):
    """Use-count formulas the SRD states as arithmetic. Formula-blanks
    discipline: no blanks supplied, no number - the formula alone."""
    aid = adapter.id
    if "feature" not in p:
        return v.cannot_adjudicate(
            "Provide a feature name.", adapter=aid,
            reason_code="missing-fact", missing_inputs=("feature",))
    feat = (p["feature"] or "").strip().lower()
    if not feat:
        return v.cannot_adjudicate(
            "Feature name must not be blank.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    if feat not in _FEATURE_USES:
        return v.cannot_adjudicate(
            f"feature must be one of {sorted(_FEATURE_USES)}; use-count tables "
            f"(not formulas) are out of scope.", adapter=aid,
            reason_code="unmodeled-rule", missing_inputs=())
    spec = _FEATURE_USES[feat]
    have = all(p.get(b) is not None for b in spec["blanks"])
    data = {"formula": spec["formula"]}
    if have:
        data["uses"] = spec["fn"](p)
        why = f"{feat}: {data['uses']} uses ({spec['formula']})."
    else:
        why = (f"{feat}: uses = {spec['formula']} - supply "
               f"{spec['blanks']} to resolve the number.")
    return v.legal(why, [v.Citation(f"SRD 5.2.1 p.{spec['page']}", spec["page"], None)],
                   aid, ["feature.uses"], data=data)
