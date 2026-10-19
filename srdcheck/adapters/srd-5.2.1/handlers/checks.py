"""Saving throws and ability checks.

Owns: save.check, check.make, concentration.check
"""

from srdcheck import verdict as v
from .common import _cite, _condition_category_gate, _effect_required_facts, _missing_fact_refusal, _path_present, event_int
from .rolls import _CHECK_MODELED, _compose
from srdcheck.adapter import Adapter
from srdcheck.verdict import Verdict


# conditions that auto-fail Strength and Dexterity saves -> the citing atom
_SAVE_AUTOFAIL_STR_DEX = {
    "paralyzed": "condition.paralyzed.saves-fail",
    "petrified": "condition.petrified.saves-fail",
    "stunned": "condition.stunned.saves-fail",
    "unconscious": "condition.unconscious.saves-fail",
}
_ABILITIES = {"str", "dex", "con", "int", "wis", "cha"}


def save_check(adapter: Adapter, p: dict) -> Verdict:
    """Adjudicate a saving throw. Optionally ability-typed and condition-aware:
    pass `save_ability` (str/dex/con/int/wis/cha) and `saver_conditions` to apply
    the codified overrides — auto-fail Str/Dex (Paralyzed/Petrified/Stunned/
    Unconscious), Disadvantage on Dex saves (Restrained), and Exhaustion's flat
    d20 penalty. The caller supplies the rolled d20 (RNG is out of scope, T6);
    the engine composes and resolves, cited."""
    a, aid = adapter.atoms, adapter.id
    atom = a["save.d20-vs-dc"]
    if "dc" not in p:
        return v.cannot_adjudicate(
            "Provide the DC.", adapter=aid, reason_code="missing-fact",
            missing_inputs=("dc",))
    # The validator deliberately follows JSON Schema: an integral JSON number
    # such as 12.0 satisfies type integer. Normalize it for handler arithmetic.
    dc = int(p["dc"])
    ability = (p.get("save_ability") or "").lower()
    if ability and ability not in _ABILITIES:
        return v.cannot_adjudicate(
            f"'{ability}' is not an ability (str/dex/con/int/wis/cha).",
            adapter=aid, reason_code="invalid-input", missing_inputs=())
    supplied_conditions = p.get("saver_conditions", [])
    if any(not c.strip() for c in supplied_conditions):
        return v.cannot_adjudicate(
            "Condition names must not be blank.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    sc = {c.lower() for c in supplied_conditions}
    for c in sc:
        categories = adapter.lookup_entity(c) or []
        if not categories:
            return v.cannot_adjudicate(
                f"'{c}' is not a condition known to this ruleset.", adapter=aid,
                reason_code="unsupported-content", missing_inputs=())
        if "condition" not in categories:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but is not a condition.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())

    # Auto-fail overrides the roll entirely (no d20 needed).
    if ability in ("str", "dex"):
        for cond, atom_id in _SAVE_AUTOFAIL_STR_DEX.items():
            if cond in sc:
                af = a[atom_id]
                return v.legal(
                    f"Automatic failure: a {cond.capitalize()} creature "
                    f"auto-fails {ability.upper()} saving throws.",
                    [_cite(af)], aid, [atom_id],
                    data={"dc": dc, "success": False, "auto_fail": True})

    # Compose Advantage/Disadvantage from conditions (caller rolls per the mode).
    adv, dis, cites, rules = [], [], [_cite(atom)], [atom["id"]]
    if ability == "dex" and "restrained" in sc:
        rs = a["condition.restrained.saves"]
        dis.append("Restrained (Dexterity save)")
        cites.append(_cite(rs))
        rules.append(rs["id"])
    mode, dice, comp = _compose(adapter, adv, dis)
    if comp:
        cites.append(_cite(comp))
        rules.append(comp["id"])

    modifier = int(p.get("modifier", 0))
    lvl = int(p.get("exhaustion_level", 0))
    if lvl:
        if not 0 <= lvl <= 6:
            return v.cannot_adjudicate(
                f"Exhaustion level {lvl} is outside the SRD range (0 to 6).",
                adapter=aid, reason_code="invalid-input", missing_inputs=())
        ex = a["condition.exhaustion.d20-penalty"]
        modifier += ex["params"]["per_level"] * lvl
        cites.append(_cite(ex))
        rules.append(ex["id"])

    d20 = event_int(p, "d20_result")
    data = {"dc": dc, "roll": mode, "d20s": dice}
    if d20 is None:
        # no roll supplied: report the composed mode + net modifier only.
        data["net_modifier"] = modifier
        return v.legal(
            f"Saving throw: roll {mode} ({dice} d20){f', {modifier:+d} modifier' if modifier else ''} "
            f"vs DC {dc}.", cites, aid, rules, data=data)
    if not 1 <= d20 <= 20:
        return v.cannot_adjudicate(
            "d20 result must be 1-20.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    total = d20 + modifier
    ok = total >= dc
    data.update(total=total, success=ok)
    return v.legal(
        f"Save total {total} (d20 {d20} {modifier:+d}) vs DC {dc}, rolled "
        f"{mode}: {'success' if ok else 'failure'}.", cites, aid, rules, data=data)


def check_make(adapter: Adapter, p: dict) -> Verdict:
    """Adjudicate an ability check (a D20 Test) against a DC, condition-aware.
    Actor conditions: Blinded/Deafened auto-fail a check that requires
    sight/hearing (pass check_requires); Poisoned/Frightened impose Disadvantage
    (Frightened gated on line of sight to the source); Exhaustion its flat d20
    penalty. On a social check where the actor is the target's charmer
    (target_charmed_by_actor + social), the actor has Advantage. Caller rolls
    (T6): with d20_result it resolves, otherwise it reports the composed mode."""
    a, aid = adapter.atoms, adapter.id
    if "dc" not in p:
        return v.cannot_adjudicate(
            "Provide the DC.", adapter=aid, reason_code="missing-fact",
            missing_inputs=("dc",))
    dc = int(p["dc"])
    ability = (p.get("ability") or "").lower()
    if ability and ability not in _ABILITIES:
        return v.cannot_adjudicate(
            f"'{ability}' is not an ability (str/dex/con/int/wis/cha).",
            adapter=aid, reason_code="invalid-input", missing_inputs=())
    conds, refusal = _condition_category_gate(
        adapter, p.get("actor_conditions", []), _CHECK_MODELED,
        "ability-check")
    if refusal is not None:
        return refusal

    missing = []
    for condition, effect in (
            ("blinded", "actor.blinded"),
            ("deafened", "actor.deafened"),
            ("frightened", "actor.frightened"),
            ("exhaustion", "actor.exhaustion")):
        if condition in conds:
            missing.extend(
                path for path in _effect_required_facts(
                    adapter, "check.make", effect)
                if not _path_present(p, path))
    charm_facts = _effect_required_facts(
        adapter, "check.make", "target.charmed-social")
    if p.get("social") is True and "target_charmed_by_actor" not in p:
        missing.append(charm_facts[1])
    if p.get("target_charmed_by_actor") is True and "social" not in p:
        missing.append(charm_facts[0])
    if missing:
        return _missing_fact_refusal(adapter, missing)

    supplied_requires = p.get("check_requires", [])
    if isinstance(supplied_requires, str):
        normalized = supplied_requires.strip().casefold()
        if normalized == "neither":
            requires = set()
        elif normalized in {"sight", "hearing"}:
            requires = {normalized}
        else:
            return v.cannot_adjudicate(
                "check_requires must be 'sight', 'hearing', 'neither', or "
                "an array containing sight and/or hearing.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
    else:
        requires = {item.casefold() for item in supplied_requires}

    if "blinded" in conds and "sight" in requires:
        bl = a["condition.blinded.cant-see"]
        return v.legal(
            "Automatic failure: a Blinded creature auto-fails a check that "
            "requires sight.", [_cite(bl)], aid, [bl["id"]],
            data={"dc": dc, "success": False, "auto_fail": True})
    if "deafened" in conds and "hearing" in requires:
        df = a["condition.deafened.cant-hear"]
        return v.legal(
            "Automatic failure: a Deafened creature auto-fails a check that "
            "requires hearing.", [_cite(df)], aid, [df["id"]],
            data={"dc": dc, "success": False, "auto_fail": True})

    adv, dis, cites, rules = [], [], [_cite(a["save.d20-vs-dc"])], ["save.d20-vs-dc"]
    if "poisoned" in conds:
        po = a["condition.poisoned.attacks"]  # covers ability checks too
        dis.append("Poisoned")
        cites.append(_cite(po))
        rules.append(po["id"])
    if "frightened" in conds and p["frightened_source_in_sight"]:
        fr = a["condition.frightened.attacks"]  # covers ability checks too
        dis.append("Frightened (source in sight)")
        cites.append(_cite(fr))
        rules.append(fr["id"])
    if p.get("target_charmed_by_actor") and p.get("social"):
        ch = a["condition.charmed.social-advantage"]
        adv.append("target is Charmed by the actor (social interaction)")
        cites.append(_cite(ch))
        rules.append(ch["id"])
    mode, dice, comp = _compose(adapter, adv, dis)
    if comp:
        cites.append(_cite(comp))
        rules.append(comp["id"])

    modifier = int(p.get("modifier", 0))
    lvl = int(p.get("exhaustion_level", 0))
    if lvl:
        if not 0 <= lvl <= 6:
            return v.cannot_adjudicate(
                f"Exhaustion level {lvl} is outside the SRD range (0 to 6).",
                adapter=aid, reason_code="invalid-input", missing_inputs=())
        ex = a["condition.exhaustion.d20-penalty"]
        modifier += ex["params"]["per_level"] * lvl
        cites.append(_cite(ex))
        rules.append(ex["id"])

    d20 = event_int(p, "d20_result")
    data = {"dc": dc, "roll": mode, "d20s": dice}
    if d20 is None:
        data["net_modifier"] = modifier
        return v.legal(
            f"Ability check: roll {mode} ({dice} d20)"
            f"{f', {modifier:+d} modifier' if modifier else ''} vs DC {dc}.",
            cites, aid, rules, data=data)
    if not 1 <= d20 <= 20:
        return v.cannot_adjudicate(
            "d20 result must be 1-20.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    total = d20 + modifier
    ok = total >= dc
    data.update(total=total, success=ok)
    return v.legal(
        f"Check total {total} (d20 {d20} {modifier:+d}) vs DC {dc}, rolled "
        f"{mode}: {'success' if ok else 'failure'}.", cites, aid, rules, data=data)


def concentration_check(adapter: Adapter, p: dict) -> Verdict:
    """Concentration save on taking damage: DC = max(10, damage // 2), capped at
    30 (SRD 5.2.1 p.179); optionally resolve the declared d20 result."""
    a, aid = adapter.atoms, adapter.id
    dc_atom, save_atom = a["save.concentration-dc"], a["save.d20-vs-dc"]
    dmg = int(p.get("damage", 0))
    if dmg < 0:
        return v.cannot_adjudicate(
            "Damage cannot be negative.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    dc = min(dc_atom["params"]["cap"], max(dc_atom["params"]["floor"], dmg // 2))
    data = {"dc": dc}
    why = f"Concentration DC is max(10, {dmg} // 2) = {dc}."
    cites = [_cite(dc_atom)]
    rules = [dc_atom["id"]]
    d20 = event_int(p, "d20_result")
    if d20 is not None:
        if not 1 <= d20 <= 20:
            return v.cannot_adjudicate(
                "d20 result must be 1-20.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        total = d20 + int(p.get("con_modifier", 0))
        ok = total >= dc
        data.update(total=total, success=ok)
        why += (f" Save total {total} vs DC {dc}: concentration "
                f"{'maintained' if ok else 'broken'}.")
        cites.append(_cite(save_atom))
        rules.append(save_atom["id"])
    return v.legal(why, cites, aid, rules, data=data)
