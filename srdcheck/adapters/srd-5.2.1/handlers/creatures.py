"""Creature identity, stat facts, and the encounter XP budget.

Owns: creature.valid, creature.stats, encounter.xp-budget
"""

from srdcheck import verdict as v
from .common import _cite
from srdcheck.adapter import Adapter
from srdcheck.verdict import Verdict


def creature_valid(adapter: Adapter, p: dict) -> Verdict:
    """Is `name` a valid SRD 5.2.1 creature? (issue #3)

    legal = a creature in 5.2.1; illegal = SRD content but not a creature
    (e.g. a spell name); cannot-adjudicate = not in the SRD at all (could be a
    2014-only name, a typo, or third-party content — this version, having only
    the 5.2.1 adapter, cannot distinguish those honestly).
    """
    aid = adapter.id
    if "name" not in p:
        return v.cannot_adjudicate(
            "No creature name provided.", adapter=aid,
            reason_code="missing-fact", missing_inputs=("name",))
    name = (p["name"] or "").strip()
    if not name:
        return v.cannot_adjudicate(
            "Creature name must not be blank.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    rec = adapter.entity_record("creature", name)
    if rec:
        return v.legal(
            f"'{rec['name']}' is a valid SRD 5.2.1 creature (CR {rec['cr']}).",
            [v.Citation(rec["citation"])], aid)
    cats = adapter.lookup_entity(name)
    if cats:
        return v.illegal(
            f"'{name}' is SRD 5.2.1 content but not a creature "
            f"(it is: {', '.join(sorted(set(cats)))}).", adapter=aid)
    return v.cannot_adjudicate(
        f"'{name}' is not a creature in SRD 5.2.1. It may be a 2014-only name, "
        "a typo, or third-party content — this version cannot distinguish "
        "those.", adapter=aid, reason_code="unsupported-content",
        missing_inputs=())


def creature_stats(adapter: Adapter, p: dict) -> Verdict:
    """Return a creature's CR/XP with citation (issue #2). Depends on #1's data."""
    aid = adapter.id
    if "name" not in p:
        return v.cannot_adjudicate(
            "No creature name provided.", adapter=aid,
            reason_code="missing-fact", missing_inputs=("name",))
    name = (p["name"] or "").strip()
    if not name:
        return v.cannot_adjudicate(
            "Creature name must not be blank.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    rec = adapter.entity_record("creature", name)
    if not rec:
        cats = adapter.lookup_entity(name)
        if cats:
            return v.cannot_adjudicate(
                f"'{name}' is SRD content but not a creature; no creature "
                "stats.", adapter=aid, reason_code="unsupported-content",
                missing_inputs=(),
                suggested_next_action="use-other-capability")
        return v.cannot_adjudicate(
            f"'{name}' is not a creature in SRD 5.2.1; no stats to return.",
            adapter=aid, reason_code="unsupported-content",
            missing_inputs=())
    return v.legal(
        f"{rec['name']}: CR {rec['cr']}, XP {rec['xp']}.",
        [v.Citation(rec["citation"])], aid,
        data={"name": rec["name"], "cr": rec["cr"], "xp": rec["xp"],
              "citation": rec["citation"]})


def encounter_xp_budget(adapter: Adapter, p: dict) -> Verdict:
    """XP budget per character for a party level + difficulty (issue #4,
    SRD 5.2.1 p.202). Optionally multiply by party_size for the total budget."""
    a, aid = adapter.atoms, adapter.id
    atom = a["encounter.xp-budget-per-character"]
    table = atom["params"]["table"]
    level = str(p.get("level", ""))
    difficulty = str(p.get("difficulty", "")).strip().lower()
    if level not in table:
        return v.cannot_adjudicate(
            f"Party level {p.get('level')!r} is outside the SRD 5.2.1 table "
            "(levels 1-20).", [_cite(atom)], aid, [atom["id"]],
            reason_code="invalid-input", missing_inputs=())
    if difficulty not in atom["params"]["difficulties"]:
        return v.cannot_adjudicate(
            f"Difficulty {p.get('difficulty')!r} is not one of "
            f"{atom['params']['difficulties']}.", [_cite(atom)], aid,
            [atom["id"]], reason_code="invalid-input", missing_inputs=())
    per_character = table[level][difficulty]
    data = {"per_character": per_character, "citation": "SRD 5.2.1 p.202"}
    why = (f"Level {level} {difficulty} encounter: {per_character} XP per "
           "character.")
    size = p.get("party_size")
    if isinstance(size, int) and size > 0:
        data["party_size"] = size
        data["total"] = per_character * size
        why += f" Total for a party of {size}: {data['total']} XP."
    return v.legal(why, [_cite(atom)], aid, [atom["id"]], data=data)
