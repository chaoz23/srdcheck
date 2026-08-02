"""Query handlers for the srd-5.2.1 adapter.

Game logic lives here, in the adapter — never in the kernel (truth T7).
Handlers read their facts from rule atoms (parameters + citations); the
control flow below is the code escape hatch the adapter spec allows.
"""

import json

from srdcheck import verdict as v
from srdcheck.schema import (ValidationIssue, issues as schema_issues,
                             normalize_integers)


def _cite(atom):
    c = atom["citation"]
    return v.Citation(f"SRD 5.2.1 p.{c['page']} '{c['section']}'",
                      c["page"], c.get("quote"))


def event_int(p, key):
    """Read an integer param, or None if absent. Keeps None distinct from 0
    (a declared d20 of 0 is invalid; an absent one means 'DC only')."""
    val = p.get(key)
    return int(val) if val is not None else None


def mage_hand_use(adapter, p):
    """p: {kind, weight_lb?, distance_ft?} — one proposed use of the hand."""
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


def _effective_speed(adapter, p, cites, rules):
    speed = p.get("speed", 0)
    for c, atom_id in _SPEED_ZERO.items():
        if c in p["_conds"]:
            atom = adapter.atoms[atom_id]
            cites.append(_cite(atom))
            rules.append(atom["id"])
            p["_speed_cause_atoms"] = [atom_id]  # so budget verdicts cite *why*
            return 0
    lvl = int(p.get("exhaustion_level", 0))
    if lvl:
        ex = adapter.atoms["condition.exhaustion.speed-reduction"]
        cites.append(_cite(ex))
        rules.append(ex["id"])
        p["_speed_cause_atoms"] = ["condition.exhaustion.speed-reduction"]
        return max(0, speed - ex["params"]["per_level"] * lvl)
    return speed


def _validated_turn_params(adapter, query_type, params):
    """Apply the published turn schema even on direct adapter dispatch.

    Engine calls already validate and normalize before reaching a handler.
    Adapters remain directly callable for conformance and embedding, so the two
    turn surfaces repeat their boundary gate here instead of trusting callers.
    """
    schema = adapter.query_meta[query_type]["inputSchema"]
    problems = schema_issues(params, schema)
    if problems:
        from srdcheck.engine import validation_refusal
        return None, validation_refusal(problems, adapter.id)
    return normalize_integers(params, schema), None


def turn_plan(adapter, p):
    """Judge a proposed own-turn plan against budgets and modeled conditions.

    params: speed, conditions[], spent{action,bonus_action,reaction,
    free_interaction,movement_ft,spell_slots_this_turn}, plan[{do,...}].
    """
    p, refusal = _validated_turn_params(adapter, "turn.plan", p)
    if refusal is not None:
        return refusal
    a = adapter.atoms
    aid = adapter.id
    if int(p.get("speed", 0)) < 0:
        return v.cannot_adjudicate(
            f"Speed {p.get('speed')} is not a valid Speed; cannot adjudicate.",
            adapter=aid, reason_code="invalid-input", missing_inputs=())
    for step in p.get("plan", []):
        lvl = step.get("spell", {}).get("level")
        if lvl is not None and not 0 <= int(lvl) <= 9:
            return v.cannot_adjudicate(
                f"Spell level {lvl} is outside the SRD range (cantrip 0 to "
                "9th level); cannot adjudicate.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
    conds = [c.strip() for c in p.get("conditions", [])]
    for c in conds:
        if not c:
            return v.cannot_adjudicate(
                "Condition names must not be blank.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        cats = adapter.lookup_entity(c) or []
        if not cats:
            return v.cannot_adjudicate(
                f"'{c}' is not a condition known to this ruleset; the plan "
                "cannot be adjudicated.", adapter=aid,
                reason_code="unsupported-content", missing_inputs=())
        if "condition" not in cats:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but is not a condition; the plan "
                "cannot be adjudicated from that input.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        if c.lower() == "exhaustion":
            if "exhaustion_level" not in p:
                return v.cannot_adjudicate(
                    "Exhaustion's Speed reduction is graduated (5 ft per "
                    "level); pass exhaustion_level (1-6) to adjudicate "
                    "movement.", adapter=aid, reason_code="missing-fact",
                    missing_inputs=("exhaustion_level",))
            if int(p["exhaustion_level"]) == 0:
                return v.cannot_adjudicate(
                    "exhaustion_level 0 contradicts an active Exhaustion "
                    "condition; remove the condition or provide level 1-6.",
                    adapter=aid,
                    reason_code="invalid-input", missing_inputs=())
        if c.lower() not in _MODELED_CONDITIONS:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but its turn-economy effects are "
                "not modeled in this adapter version; refusing rather than "
                "risking a wrong verdict.", adapter=aid,
                reason_code="unmodeled-rule", missing_inputs=())
    p = dict(p)
    p["_conds"], p["_embeds"] = _expand_conditions({c.lower() for c in conds})

    inc = a["condition.incapacitated.inactive"]
    spent = dict(p.get("spent", {}))
    budgets = {
        "action": 1 - int(bool(spent.get("action"))),
        "bonus_action": 1 - int(bool(spent.get("bonus_action"))),
        "reaction": 1 - int(bool(spent.get("reaction"))),
        "free_interaction": 1 - int(bool(spent.get("free_interaction"))),
        "spell_slots": 1 - int(spent.get("spell_slots_this_turn", 0)),
    }
    budget_atoms = {"action": "turn.one-action",
                    "bonus_action": "turn.one-bonus-action",
                    "reaction": "turn.one-reaction-per-round",
                    "free_interaction": "turn.one-free-interaction",
                    "spell_slots": "spell.one-slot-per-turn"}
    step_budget = {"action": "action", "bonus-action": "bonus_action",
                   "reaction": "reaction", "free-interaction": "free_interaction"}

    cites, rules = [], []
    prone = "prone" in p["_conds"]
    speed = _effective_speed(adapter, p, cites, rules)
    moved = int(spent.get("movement_ft", 0))

    for i, step in enumerate(p.get("plan", []), 1):
        do = step.get("do")
        if do in ("action", "bonus-action", "reaction"):
            if "incapacitated" in p["_conds"]:
                ic = [_cite(inc)] + [_cite(a[e]) for e in p["_embeds"]]
                ir = [inc["id"]] + list(p["_embeds"])
                return v.illegal(
                    f"Step {i} ({do}): {inc['citation']['quote']}",
                    ic, aid, ir)
            b = step_budget[do]
            if budgets[b] < 1:
                atom = a[budget_atoms[b]]
                return v.illegal(
                    f"Step {i}: no {do} remains this turn. "
                    f"{atom['citation']['quote']}",
                    [_cite(atom)], aid, [atom["id"]])
            budgets[b] -= 1
            level = step.get("spell", {}).get("level", 0)
            if level > 0:
                if budgets["spell_slots"] < 1:
                    atom = a["spell.one-slot-per-turn"]
                    return v.illegal(
                        f"Step {i}: a second spell slot this turn. "
                        f"{atom['citation']['quote']}",
                        [_cite(atom)], aid, [atom["id"]])
                budgets["spell_slots"] -= 1
        elif do == "free-interaction":
            if budgets["free_interaction"] < 1:
                atom = a["turn.one-free-interaction"]
                return v.illegal(
                    f"Step {i}: a second free object interaction. "
                    f"{atom['citation']['quote']}",
                    [_cite(atom)], aid, [atom["id"]])
            budgets["free_interaction"] -= 1
        elif do == "stand-up":
            pr = a["condition.prone.movement"]
            if not prone:
                return v.cannot_adjudicate(
                    f"Step {i}: standing up without the Prone condition has "
                    "no cost in the rules text; nothing to adjudicate.",
                    adapter=aid, reason_code="invalid-input",
                    missing_inputs=())
            if speed == 0:
                return v.illegal(
                    f"Step {i}: {pr['citation']['quote']}",
                    [_cite(pr)], aid, [pr["id"]])
            cost = speed // 2
            if moved + cost > speed:
                return v.illegal(
                    f"Step {i}: standing costs half Speed ({cost} ft); only "
                    f"{speed - moved} ft of movement remains.",
                    [_cite(pr)], aid, [pr["id"]])
            moved += cost
            prone = False
            cites.append(_cite(pr))
            rules.append(pr["id"])
        elif do == "move":
            feet = int(step.get("feet", 0))
            crawl = bool(step.get("crawl"))
            difficult = bool(step.get("difficult_terrain"))
            if prone and not crawl:
                pr = a["condition.prone.movement"]
                return v.illegal(
                    f"Step {i}: moving while Prone without crawling. "
                    f"{pr['citation']['quote']}",
                    [_cite(pr)], aid, [pr["id"]])
            # each "1 extra foot" cost is additive (crawling in Difficult Terrain
            # = 2 extra feet per foot, per the Crawling rule).
            cost = feet * (1 + int(crawl) + int(difficult))
            cost_atoms = []
            if crawl:
                cost_atoms.append("movement.crawling-cost")
            if difficult:
                cost_atoms.append("movement.difficult-terrain")
            for cid in cost_atoms:
                cites.append(_cite(a[cid]))
                rules.append(cid)
            mb = a["turn.movement-budget"]
            if moved + cost > speed:
                mcites, mrules = [_cite(mb)], [mb["id"]]
                for sz in list(p.get("_speed_cause_atoms", [])) + cost_atoms:
                    mcites.append(_cite(a[sz]))
                    mrules.append(sz)
                return v.illegal(
                    f"Step {i}: {feet} ft ({cost} ft of movement) exceeds the "
                    f"remaining budget ({speed - moved} of {speed} ft). "
                    f"{mb['citation']['quote']}",
                    mcites, aid, mrules)
            moved += cost
        else:
            return v.cannot_adjudicate(
                f"Step {i}: '{do}' is not a turn component this adapter "
                "models; an improvised activity must be resolved as a table "
                "ruling by the authorized DM, including the calling agent "
                "when it is the DM.", adapter=aid,
                reason_code="gm-discretion", missing_inputs=())

    bu = a["turn.break-up-move"]
    cites.append(_cite(bu))
    rules.append(bu["id"])
    return v.legal(
        f"Action economy is legal: {moved} of {speed} ft of movement, one "
        "action / bonus action / reaction / free interaction each at most, "
        "one spell slot at most, movement may be split around actions. This "
        "checks the turn's economy only — it does not verify that a feature "
        "grants a given action (e.g. two-weapon fighting or Extra Attack "
        "prerequisites), which the SRD leaves to the character's features.",
        cites, aid, rules)


def reaction_available(adapter, p):
    """params: {spent_since_turn_start: bool, conditions: []}."""
    a, aid = adapter.atoms, adapter.id
    supplied = [c.strip() for c in p.get("conditions", [])]
    for condition in supplied:
        if not condition:
            return v.cannot_adjudicate(
                "Condition names must not be blank.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        categories = adapter.lookup_entity(condition) or []
        if "condition" not in categories:
            if categories:
                return v.cannot_adjudicate(
                    f"'{condition}' is known content, but is not a condition; "
                    "reaction availability cannot be adjudicated from that "
                    "input.", adapter=aid, reason_code="invalid-input",
                    missing_inputs=())
            return v.cannot_adjudicate(
                f"'{condition}' is not a condition known to this ruleset; "
                "reaction availability cannot be adjudicated from that input.",
                adapter=aid, reason_code="unsupported-content",
                missing_inputs=())
    conds, embeds = _expand_conditions({c.lower() for c in supplied})
    if "incapacitated" in conds:
        inc = a["condition.incapacitated.inactive"]
        citations = [_cite(inc)] + [_cite(a[atom_id]) for atom_id in embeds]
        rule_ids = [inc["id"]] + embeds
        return v.illegal(
            "An active condition includes Incapacitated. "
            + inc["citation"]["quote"], citations, aid, rule_ids)
    ra = a["turn.one-reaction-per-round"]
    if p.get("spent_since_turn_start"):
        return v.illegal(
            "The Reaction is spent. " + ra["citation"]["quote"],
            [_cite(ra)], aid, [ra["id"]])
    return v.legal(
        "A Reaction is available — including on your own turn. "
        + ra["citation"]["quote"], [_cite(ra)], aid, [ra["id"]])


def _condition_gate(adapter, p):
    """Shared jurisdiction gate for turn-state queries. None = pass."""
    for c in [x.strip() for x in p.get("conditions", [])]:
        if not c:
            return v.cannot_adjudicate(
                "Condition names must not be blank.", adapter=adapter.id,
                reason_code="invalid-input", missing_inputs=())
        categories = adapter.lookup_entity(c) or []
        if not categories:
            return v.cannot_adjudicate(
                f"'{c}' is not a condition known to this ruleset.",
                adapter=adapter.id, reason_code="unsupported-content",
                missing_inputs=())
        if "condition" not in categories:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but is not a condition.",
                adapter=adapter.id, reason_code="invalid-input",
                missing_inputs=())
        if c.lower() == "exhaustion":
            if "exhaustion_level" not in p:
                return v.cannot_adjudicate(
                    "Exhaustion's Speed reduction is graduated (5 ft per "
                    "level); pass exhaustion_level (1-6) to adjudicate "
                    "movement.", adapter=adapter.id,
                    reason_code="missing-fact",
                    missing_inputs=("exhaustion_level",))
            if int(p["exhaustion_level"]) == 0:
                return v.cannot_adjudicate(
                    "exhaustion_level 0 contradicts an active Exhaustion "
                    "condition; remove the condition or provide level 1-6.",
                    adapter=adapter.id,
                    reason_code="invalid-input", missing_inputs=())
        if c.lower() not in _MODELED_CONDITIONS:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but its turn-economy effects are "
                "not modeled in this adapter version; refusing rather than "
                "risking a wrong verdict.", adapter=adapter.id,
                reason_code="unmodeled-rule", missing_inputs=())
    return None


def turn_options(adapter, p):
    """T5: enumerate what remains legal this turn given the same state
    shape turn.plan takes (speed, conditions, spent) — no plan."""
    p, refusal = _validated_turn_params(adapter, "turn.options", p)
    if refusal is not None:
        return refusal
    gate = _condition_gate(adapter, p)
    if gate:
        return gate
    a, aid = adapter.atoms, adapter.id
    conds, embeds = _expand_conditions(
        {c.strip().lower() for c in p.get("conditions", [])})
    p = dict(p)
    p["_conds"] = conds
    spent = dict(p.get("spent", {}))
    cites, rules, options, notes = [], [], [], []

    def add_cite(atom_id):
        atom = a[atom_id]
        cites.append(_cite(atom))
        rules.append(atom_id)

    incapacitated = "incapacitated" in conds
    if incapacitated:
        add_cite("condition.incapacitated.inactive")
        for e in embeds:
            add_cite(e)
        notes.append("Incapacitated: no action, Bonus Action, or Reaction — "
                     "movement is not blocked by this condition.")
    else:
        slot_left = int(spent.get("spell_slots_this_turn", 0)) < 1
        if not spent.get("action"):
            options.append({"do": "action", "spell_slot_available": slot_left})
        if not spent.get("bonus_action"):
            options.append({"do": "bonus-action",
                            "spell_slot_available": slot_left})
        if not spent.get("reaction"):
            options.append({"do": "reaction", "spell_slot_available": slot_left,
                            "note": "usable on your own turn"})

    if not spent.get("free_interaction"):
        options.append({"do": "free-interaction"})

    speed = p.get("speed", 0)
    zeroed = False
    for c, atom_id in _SPEED_ZERO.items():
        if c in conds:
            add_cite(atom_id)
            speed = 0
            zeroed = True
            break
    lvl = int(p.get("exhaustion_level", 0))
    if lvl and not zeroed:
        ex = a["condition.exhaustion.speed-reduction"]
        add_cite(ex["id"])
        speed = max(0, speed - ex["params"]["per_level"] * lvl)
    left = max(0, speed - int(spent.get("movement_ft", 0)))
    prone = "prone" in conds
    if prone:
        add_cite("condition.prone.movement")
        if left >= 2:
            add_cite("movement.crawling-cost")
            options.append({"do": "move", "mode": "crawl",
                            "feet_remaining": left // 2})
        stand_cost = speed // 2
        if speed > 0 and left >= stand_cost:
            options.append({"do": "stand-up", "cost_ft": stand_cost})
        elif speed == 0:
            notes.append("Speed 0: cannot right yourself from Prone.")
    elif left > 0:
        add_cite("turn.movement-budget")
        options.append({"do": "move", "mode": "walk", "feet_remaining": left})

    why = (f"{len(options)} option kinds remain this turn."
           + (" " + " ".join(notes) if notes else ""))
    return v.legal(why, cites, aid, rules, data={"options": options})


# Attack-roll modifier composition. Conditions whose attack effects this
# adapter version models; anything else known yields exit 2 (T1/T8).
_ATTACK_MODELED = {"prone", "invisible", "blinded", "restrained", "paralyzed",
                   "stunned", "grappled", "incapacitated",
                   # completeness pass: every SRD condition with a codified
                   # attack-roll / attack-legality effect (or none) is handled,
                   # so none is silently refused as merely unbuilt.
                   "frightened", "poisoned", "charmed", "deafened",
                   "petrified", "unconscious",
                   # Exhaustion's attack penalty is graduated: it comes through
                   # the exhaustion_level param, not adv/disadv from the bare
                   # name. Listed here so the name isn't refused as unbuilt.
                   "exhaustion"}
_CHECK_MODELED = set(_MODELED_CONDITIONS)


def _compose(adapter, adv, dis):
    """Fold source lists through the p.8 composition atoms."""
    a = adapter.atoms
    if adv and dis:
        atom = a["roll.both-cancel"]
        return "straight", 1, atom
    if adv:
        atom = a["roll.dont-stack"] if len(adv) > 1 else a["roll.advantage-mechanic"]
        return "advantage", 2, atom
    if dis:
        atom = a["roll.dont-stack"] if len(dis) > 1 else a["roll.advantage-mechanic"]
        return "disadvantage", 2, atom
    return "straight", 1, None


def roll_compose(adapter, p):
    """Pure composition: {advantage_sources: [..], disadvantage_sources: [..],
    reroll_available?: bool} -> net roll mode."""
    adv = list(p.get("advantage_sources", []))
    dis = list(p.get("disadvantage_sources", []))
    mode, dice, atom = _compose(adapter, adv, dis)
    cites, rules = [], []
    if atom:
        cites, rules = [_cite(atom)], [atom["id"]]
    data = {"roll": mode, "d20s": dice,
            "advantage_sources": adv, "disadvantage_sources": dis}
    why = (f"{len(adv)} Advantage source(s) and {len(dis)} Disadvantage "
           f"source(s) compose to: {mode} ({dice} d20).")
    if p.get("reroll_available"):
        rr = adapter.atoms["roll.reroll-one-die"]
        cites.append(_cite(rr))
        rules.append(rr["id"])
        data["reroll_note"] = "reroll or replace only one die, not both"
    return v.legal(why, cites, adapter.id, rules, data=data)


def attack_modifiers(adapter, p):
    """Compose an attack roll's Advantage/Disadvantage from modeled conditions.

    params: attacker{conditions[], exhaustion_level?, can_be_seen_by_target?},
    target{conditions[], is_grappler_of_attacker?, can_see_attacker...},
    distance_ft.
    """
    a, aid = adapter.atoms, adapter.id
    atk = p.get("attacker", {})
    tgt = p.get("target", {})
    exl = int(atk.get("exhaustion_level", 0))
    if not 0 <= exl <= 6:
        return v.cannot_adjudicate(
            f"Exhaustion level {exl} is outside the SRD range (0 to 6; a "
            "creature dies at 6); cannot adjudicate.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    ac, refusal = _condition_category_gate(
        adapter, atk.get("conditions", []), _ATTACK_MODELED, "attack-roll")
    if refusal is not None:
        return refusal
    tc, refusal = _condition_category_gate(
        adapter, tgt.get("conditions", []), _ATTACK_MODELED, "attack-roll")
    if refusal is not None:
        return refusal

    missing = []
    for condition, effect in (
            ("charmed", "attacker.charmed"),
            ("frightened", "attacker.frightened"),
            ("grappled", "attacker.grappled"),
            ("invisible", "attacker.invisible"),
            ("exhaustion", "attacker.exhaustion")):
        if condition in ac:
            missing.extend(
                path for path in _effect_required_facts(
                    adapter, "attack.modifiers", effect)
                if not _path_present(p, path))
    if "invisible" in tc:
        missing.extend(
            path for path in _effect_required_facts(
                adapter, "attack.modifiers", "target.invisible")
            if not _path_present(p, path))

    nearby_states = []
    if p.get("ranged"):
        missing.extend(
            path for path in _query_required_facts(
                adapter, "attack.modifiers", "ranged.close-combat")
            if not _path_present(p, path))
        for index, enemy in enumerate(p.get("nearby_enemies", [])):
            prefix = f"nearby_enemies[{index}]"
            if "can_see_attacker" not in enemy:
                missing.append(f"{prefix}.can_see_attacker")
            if (enemy.get("can_see_attacker") is True
                    and "conditions" not in enemy):
                missing.append(f"{prefix}.conditions")
            supplied = enemy.get("conditions", [])
            enemy_conditions, refusal = _condition_category_gate(
                adapter, supplied, _ATTACK_MODELED,
                "ranged-close-combat")
            if refusal is not None:
                return refusal
            expanded, embed_atoms = _expand_conditions(enemy_conditions)
            nearby_states.append((enemy, expanded, embed_atoms))
    if missing:
        return _missing_fact_refusal(adapter, missing)

    dist = p.get("distance_ft", 5)
    adv, dis, cites, rules = [], [], [], []

    def cite_rule(atom_id):
        if atom_id not in rules:
            atom = a[atom_id]
            cites.append(_cite(atom))
            rules.append(atom_id)

    def hit(atom_id, side_list, label):
        side_list.append(label)
        cite_rule(atom_id)

    # Charmed is a legality question, not a modifier: a Charmed attacker can't
    # attack the charmer. The dependency contract requires the relationship
    # fact so an omitted observation cannot silently mean "not the charmer."
    if "charmed" in ac and tgt.get("is_charmer_of_attacker"):
        atom = a["condition.charmed.cant-harm-charmer"]
        return v.illegal(
            "The attacker is Charmed by the target: it can't attack the charmer.",
            [_cite(atom)], aid, [atom["id"]])
    if "frightened" in ac:
        if atk["frightened_source_in_sight"]:
            hit("condition.frightened.attacks", dis,
                "attacker is Frightened and the source of fear is in sight")
        else:
            atom = a["condition.frightened.attacks"]
            cites.append(_cite(atom))
            rules.append(atom["id"])  # cited, but no Disadvantage: source unseen
    if "poisoned" in ac:
        hit("condition.poisoned.attacks", dis, "attacker is Poisoned")
    if p.get("ranged"):
        # a ranged attack has Disadvantage if a seeing, non-Incapacitated enemy
        # is within 5 ft. The caller supplies who is within 5 ft (geometry, T6);
        # srdcheck applies the can-see + not-Incapacitated rule.
        cite_rule("attack.ranged-in-close-combat")
        threatening = []
        for enemy, conditions, embed_atoms in nearby_states:
            if enemy["can_see_attacker"] and "incapacitated" not in conditions:
                threatening.append(enemy)
            elif enemy["can_see_attacker"]:
                for atom_id in embed_atoms:
                    cite_rule(atom_id)
        if threatening:
            dis.append(
                "ranged attack within 5 ft of a seeing, non-Incapacitated enemy")

    if "prone" in ac:
        hit("condition.prone.attacks", dis, "attacker is Prone")
    if "blinded" in ac:
        hit("condition.blinded.attacks", dis, "attacker is Blinded")
    if "restrained" in ac:
        hit("condition.restrained.attacks", dis, "attacker is Restrained")
    if "grappled" in ac and not tgt["is_grappler_of_attacker"]:
        hit("condition.grappled.attacks", dis,
            "attacker is Grappled, target is not the grappler")
    if atk.get("unseen_by_target") and not tgt.get("can_see_attacker"):
        hit("attack.unseen-attacker", adv, "attacker is unseen by the target")
    if tgt.get("unseen_by_attacker") and not atk.get("can_see_target"):
        hit("attack.unseen-target", dis, "target is unseen by the attacker")
    if "invisible" in ac:
        if tgt["can_see_attacker"]:
            atom = a["condition.invisible.attacks"]
            cites.append(_cite(atom))
            rules.append(atom["id"])
        else:
            hit("condition.invisible.attacks", adv, "attacker is Invisible")

    if "prone" in tc:
        if dist <= a["condition.prone.attacks"]["params"]["against_adv_within_ft"]:
            hit("condition.prone.attacks", adv,
                f"target is Prone, attacker within 5 ft ({dist} ft)")
        else:
            hit("condition.prone.attacks", dis,
                f"target is Prone, attacker beyond 5 ft ({dist} ft)")
    for cond, atom_id in (("blinded", "condition.blinded.attacks"),
                          ("restrained", "condition.restrained.attacks"),
                          ("paralyzed", "condition.paralyzed.attacks"),
                          ("stunned", "condition.stunned.attacks"),
                          ("petrified", "condition.petrified.attacks"),
                          ("unconscious", "condition.unconscious.attacks")):
        if cond in tc:
            hit(atom_id, adv, f"target is {cond.capitalize()}")
    auto_crit = None
    for cond, atom_id in (("unconscious", "condition.unconscious.auto-crit"),
                          ("paralyzed", "condition.paralyzed.auto-crit")):
        if cond in tc:
            crit = a[atom_id]
            if dist <= crit["params"]["within_ft"]:
                auto_crit = (f"target is {cond.capitalize()} and the attacker is "
                             f"within {crit['params']['within_ft']} ft ({dist} ft)"
                             ": a hit is a Critical Hit")
                cites.append(_cite(crit))
                rules.append(crit["id"])
            break
    if "invisible" in tc:
        if atk["can_see_target"]:
            atom = a["condition.invisible.attacks"]
            return v.cannot_adjudicate(
                "The target is Invisible but the attacker can somehow see it. "
                "The condition text says the Invisible creature doesn't gain "
                "'this benefit' against a creature that can see it — whether "
                "that clause covers the Disadvantage on attacks against it is "
                "genuinely ambiguous in the rules text. The authorized DM, "
                "including the calling agent when it is the DM, resolves the "
                "table ruling.", [_cite(atom)], aid, [atom["id"]],
                reason_code="rules-ambiguous", missing_inputs=())
        hit("condition.invisible.attacks", dis, "target is Invisible")

    mode, dice, comp = _compose(adapter, adv, dis)
    if comp:
        cites.append(_cite(comp))
        rules.append(comp["id"])
    data = {"roll": mode, "d20s": dice,
            "advantage_sources": adv, "disadvantage_sources": dis,
            "flat_modifiers": []}
    if auto_crit:
        data["auto_crit_on_hit"] = auto_crit
    lvl = int(atk.get("exhaustion_level", 0))
    if lvl:
        ex = a["condition.exhaustion.d20-penalty"]
        data["flat_modifiers"].append(
            {"value": ex["params"]["per_level"] * lvl,
             "source": f"Exhaustion level {lvl}"})
        cites.append(_cite(ex))
        rules.append(ex["id"])
    why = f"Attack roll: {mode} ({dice} d20)."
    if data["flat_modifiers"]:
        why += f" Flat modifier {data['flat_modifiers'][0]['value']} (Exhaustion)."
    if auto_crit:
        why += f" A hit is a Critical Hit ({auto_crit.split(': ')[0]})."
    return v.legal(why, cites, aid, rules, data=data)


# The reducer (Epic 2 / T14). The model declares; the ledger derives.
# Stunned/Paralyzed embed Incapacitated (cited atoms); unknown or unmodeled
# conditions refuse rather than record state we would later misjudge.
_STATE_CONDITIONS = {"grappled", "prone", "incapacitated", "invisible",
                     "blinded", "restrained", "stunned", "paralyzed",
                     "frightened", "poisoned", "charmed", "deafened",
                     "petrified", "unconscious", "exhaustion"}
_EMBEDS_INCAPACITATED = {"incapacitated": None,
                         "stunned": "condition.stunned.incapacitated",
                         "paralyzed": "condition.paralyzed.incapacitated",
                         "petrified": "condition.petrified.incapacitated",
                         "unconscious": "condition.unconscious.inert"}

_FRESH_TURN = {"action_spent": False, "bonus_action_spent": False,
               "reaction_spent": False, "free_interaction_spent": False,
               "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0}


def _state_schema(adapter):
    """Load the packaged canonical state contract for reducer validation."""
    return json.loads(
        (adapter.root / "state_schema.json").read_text(encoding="utf-8")
    )["schema"]


def _invalid_state(adapter_id, problems, subject="state"):
    rendered = [str(problem) for problem in problems]
    return v.cannot_adjudicate(
        f"Invalid {subject}; correct it before applying the event: "
        + "; ".join(rendered),
        adapter=adapter_id,
        data={"validation_errors": rendered},
        reason_code="invalid-input", missing_inputs=())


def _missing_event_facts(adapter_id, event_type, paths):
    return v.cannot_adjudicate(
        f"The {event_type} event needs: {', '.join(paths)}.",
        adapter=adapter_id, reason_code="missing-fact",
        missing_inputs=paths)


def _missing_paths(state, event, paths):
    roots = {"state": state, "event": event}
    missing = []
    for path in paths:
        root, key = path.split(".", 1)
        if key not in roots[root]:
            missing.append(path)
    return missing


def _blank_state_issues(state, path="state"):
    problems = []
    seen_conditions = {}
    for field in ("conditions", "resistances", "immunities",
                  "vulnerabilities"):
        for index, value in enumerate(state.get(field, [])):
            if isinstance(value, str):
                item_path = f"{path}.{field}[{index}]"
                if not value.strip():
                    problems.append(ValidationIssue(
                        item_path, "min-length", "value must not be blank"))
                elif value != value.strip():
                    problems.append(ValidationIssue(
                        item_path, "canonical-token",
                        "value must not have leading or trailing whitespace"))
                if field == "conditions" and value.strip():
                    key = value.strip().casefold()
                    if key in seen_conditions:
                        problems.append(ValidationIssue(
                            item_path, "duplicate-condition",
                            "duplicates condition at "
                            f"{path}.conditions[{seen_conditions[key]}]"))
                    else:
                        seen_conditions[key] = index
    concentration = state.get("concentration_on")
    if isinstance(concentration, str):
        if not concentration.strip():
            problems.append(ValidationIssue(
                f"{path}.concentration_on", "min-length",
                "value must not be blank"))
        elif concentration != concentration.strip():
            problems.append(ValidationIssue(
                f"{path}.concentration_on", "canonical-token",
                "value must not have leading or trailing whitespace"))
    lineage = state.get("lineage") or {}
    for field in ("prev", "self"):
        value = lineage.get(field)
        if isinstance(value, str) and not value.strip():
            problems.append(ValidationIssue(
                f"{path}.lineage.{field}", "min-length",
                "value must not be blank"))
    for index, value in enumerate(lineage.get("rule_ids", [])):
        if isinstance(value, str) and not value.strip():
            problems.append(ValidationIssue(
                f"{path}.lineage.rule_ids[{index}]", "min-length",
                "value must not be blank"))
    return problems


def _state_condition_refusal(adapter, state, path="state.conditions"):
    state_path = (path[:-len(".conditions")]
                  if path.endswith(".conditions") else "state")
    exhaustion_present = False
    for index, name in enumerate(state.get("conditions", [])):
        categories = adapter.lookup_entity(name) or []
        item_path = f"{path}[{index}]"
        if not categories:
            return v.cannot_adjudicate(
                f"{item_path} names '{name}', which is not a condition known "
                "to this ruleset.", adapter=adapter.id,
                reason_code="unsupported-content", missing_inputs=())
        if "condition" not in categories:
            return v.cannot_adjudicate(
                f"{item_path} names '{name}', which is known content but not "
                "a condition.", adapter=adapter.id,
                reason_code="invalid-input", missing_inputs=())
        lower_name = name.lower()
        if lower_name not in _STATE_CONDITIONS:
            return v.cannot_adjudicate(
                f"{item_path} names the real condition '{name}', but its "
                "state interactions are not modeled in this adapter version.",
                adapter=adapter.id, reason_code="unmodeled-rule",
                missing_inputs=())
        if lower_name == "exhaustion":
            exhaustion_present = True
            level_path = f"{state_path}.exhaustion_level"
            if "exhaustion_level" not in state:
                return v.cannot_adjudicate(
                    "Active Exhaustion needs its explicit level (1-6).",
                    adapter=adapter.id, reason_code="missing-fact",
                    missing_inputs=(level_path,))
            if state["exhaustion_level"] == 0:
                return _invalid_state(
                    adapter.id, (ValidationIssue(
                        level_path, "condition-consistency",
                        "level 0 contradicts an active Exhaustion condition"),))
    if state.get("exhaustion_level", 0) > 0 and not exhaustion_present:
        return _invalid_state(
            adapter.id, (ValidationIssue(
                f"{state_path}.exhaustion_level", "condition-consistency",
                "a positive level requires the Exhaustion condition"),))
    return None


def _event_condition_refusal(adapter, name, path="event.name"):
    """Validate an event condition name before state membership is tested."""
    if not name:
        return v.cannot_adjudicate(
            f"{path} must not be blank.", adapter=adapter.id,
            reason_code="invalid-input", missing_inputs=())
    categories = adapter.lookup_entity(name) or []
    if not categories:
        return v.cannot_adjudicate(
            f"{path} names '{name}', which is not a condition known to this "
            "ruleset.", adapter=adapter.id,
            reason_code="unsupported-content", missing_inputs=())
    if "condition" not in categories:
        return v.cannot_adjudicate(
            f"{path} names '{name}', which is known content but not a "
            "condition.", adapter=adapter.id,
            reason_code="invalid-input", missing_inputs=())
    if name.lower() not in _STATE_CONDITIONS:
        return v.cannot_adjudicate(
            f"{path} names the real condition '{name}', but its state "
            "interactions are not modeled in this adapter version.",
            adapter=adapter.id,
            reason_code="unmodeled-rule", missing_inputs=())
    return None


def _state_lifecycle_refusal(adapter, state, path="state"):
    """Reject contradictions provable from supplied lifecycle facts only."""
    hp = state.get("hp")
    missing = []
    if state.get("death_save_successes") == 3 and "stable" not in state:
        missing.append(f"{path}.stable")
    if state.get("death_save_failures") == 3 and "dead" not in state:
        missing.append(f"{path}.dead")
    if (hp == 0 and state.get("is_monster") is True
            and "dead" not in state
            and f"{path}.dead" not in missing):
        missing.append(f"{path}.dead")
    if missing:
        return v.cannot_adjudicate(
            "Lifecycle state needs its explicit resulting flags.",
            adapter=adapter.id, reason_code="missing-fact",
            missing_inputs=missing)

    problems = []
    hp_max = state.get("hp_max")
    if hp is not None and hp_max is not None and hp > hp_max:
        problems.append(ValidationIssue(
            f"{path}.hp", "lifecycle-consistency",
            "current HP must not exceed hp_max"))
    if state.get("dead") is True and hp is not None and hp > 0:
        problems.append(ValidationIssue(
            f"{path}.dead", "lifecycle-consistency",
            "a dead creature cannot have positive HP"))
    if state.get("stable") is True and hp is not None and hp > 0:
        problems.append(ValidationIssue(
            f"{path}.stable", "lifecycle-consistency",
            "a positive-HP creature cannot be in the Stable-at-0 state"))
    if state.get("dead") is True and state.get("stable") is True:
        problems.append(ValidationIssue(
            f"{path}.stable", "lifecycle-consistency",
            "a dead creature cannot also be Stable"))
    for counter in ("death_save_successes", "death_save_failures"):
        if hp is not None and hp > 0 and state.get(counter, 0) > 0:
            problems.append(ValidationIssue(
                f"{path}.{counter}", "lifecycle-consistency",
                "a positive-HP creature cannot retain death-save counters"))
    if (state.get("death_save_successes") == 3
            and state.get("stable") is not True):
        problems.append(ValidationIssue(
            f"{path}.stable", "lifecycle-consistency",
            "three death-save successes require Stable true"))
    if (state.get("death_save_failures") == 3
            and state.get("dead") is not True):
        problems.append(ValidationIssue(
            f"{path}.dead", "lifecycle-consistency",
            "three death-save failures require dead true"))
    return _invalid_state(adapter.id, problems) if problems else None


_EVENT_FIELDS = {
    "turn-start": {"type"},
    "round-advance": {"type"},
    "action": {"type", "spell", "concentration_on"},
    "bonus-action": {"type", "spell", "concentration_on"},
    "reaction": {"type", "spell", "concentration_on"},
    "free-interaction": {"type"},
    "move": {"type", "feet", "crawl"},
    "stand-up": {"type"},
    "condition-gained": {"type", "name"},
    "condition-ended": {"type", "name"},
    "damage": {"type", "amount", "crit", "damage_type"},
    "heal": {"type", "amount"},
    "death-save": {"type", "result"},
    "ruling": {"type", "note", "state_patch"},
}


def _state_to_plan_params(state):
    t = state.get("turn", {})
    params = {"speed": state.get("speed", 0),
              "conditions": state.get("conditions", []),
              "spent": {"action": t.get("action_spent"),
                        "bonus_action": t.get("bonus_action_spent"),
                        "reaction": t.get("reaction_spent"),
                        "free_interaction": t.get("free_interaction_spent"),
                        "movement_ft": t.get("movement_ft_spent", 0),
                        "spell_slots_this_turn":
                            t.get("spell_slots_spent_this_turn", 0)}}
    if "exhaustion_level" in state:
        params["exhaustion_level"] = state["exhaustion_level"]
    return params


def event_apply(adapter, p):
    """fold(state, declared_event) -> verdict (+ data.next_state on exit 0).

    Never produces an event, never advances time on its own, never rolls.
    """
    from srdcheck import lineage
    from srdcheck.engine import validation_refusal
    a, aid = adapter.atoms, adapter.id
    outer_problems = schema_issues(
        p, adapter.query_meta["event.apply"]["inputSchema"])
    if outer_problems:
        return validation_refusal(outer_problems, aid)
    try:
        json.dumps(p, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return _invalid_state(
            aid, (ValidationIssue(
                "$", "json-value",
                "request must contain only finite JSON values"),),
            subject="event.apply request")
    state = p.get("state") or {}
    event = p.get("event") or {}
    etype = event.get("type")
    irrelevant = sorted(set(event) - _EVENT_FIELDS[etype])
    if irrelevant:
        return validation_refusal([
            ValidationIssue(
                f"$.event.{field}", "additional-property",
                f"field is not allowed for a {etype} event")
            for field in irrelevant
        ], aid)
    canonical_state_schema = _state_schema(adapter)
    state_problems = schema_issues(
        state, canonical_state_schema, path="state")
    if state_problems:
        return _invalid_state(aid, state_problems)
    # The engine normalizes declared query-schema integers before dispatch.
    # state is intentionally shallow there (the complete schema is adapter
    # owned), so canonicalize its accepted JSON Schema integers here too.
    state = normalize_integers(state, canonical_state_schema)
    blank_problems = _blank_state_issues(state)
    if blank_problems:
        return _invalid_state(aid, blank_problems)
    condition_refusal = _state_condition_refusal(adapter, state)
    if condition_refusal is not None:
        return condition_refusal
    lifecycle_refusal = _state_lifecycle_refusal(adapter, state)
    if lifecycle_refusal is not None:
        return lifecycle_refusal
    if ("lineage" in state
            and state["lineage"]["self"] != lineage.canon_hash(state)):
        return _invalid_state(
            aid, (ValidationIssue(
                "state.lineage.self", "lineage-integrity",
                "does not match the canonical hash of this state"),))

    if "concentration_on" in event:
        concentration = event["concentration_on"]
        if (not concentration.strip()
                or concentration != concentration.strip()):
            return v.cannot_adjudicate(
                "event.concentration_on must be nonblank and have no "
                "surrounding whitespace.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        if "spell" not in event:
            return _missing_event_facts(
                aid, etype, ("event.spell",))
    if "damage_type" in event:
        damage_type = event["damage_type"]
        if not damage_type.strip() or damage_type != damage_type.strip():
            return v.cannot_adjudicate(
                "event.damage_type must be nonblank and have no surrounding "
                "whitespace when supplied.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
    if "name" in event:
        name = event["name"]
        if name and name != name.strip():
            return v.cannot_adjudicate(
                "event.name must not have leading or trailing whitespace.",
                adapter=aid, reason_code="invalid-input", missing_inputs=())

    required = {
        "move": ("event.feet",),
        "condition-gained": ("event.name",),
        "condition-ended": ("event.name",),
        "damage": ("event.amount",),
        "heal": ("event.amount",),
        "ruling": ("event.note",),
    }.get(etype, ())
    missing = _missing_paths(state, event, required)
    if missing:
        return _missing_event_facts(aid, etype, missing)

    nxt = json.loads(json.dumps(state)) if state else {}
    cites, rules, kind = [], [], "rule"

    def grab(atom_id):
        cites.append(_cite(a[atom_id]))
        rules.append(atom_id)

    if etype == "turn-start":
        nxt["turn"] = dict(_FRESH_TURN)
        grab("turn.one-reaction-per-round")
        why = ("Turn begins: action, Bonus Action, interaction, and movement "
               "budgets reset; the Reaction returns at the start of your turn.")
    elif etype == "round-advance":
        why = ("Round advances: no per-round state is modeled in this adapter "
               "version (durations are the caller's clock).")
    elif etype in ("action", "bonus-action", "reaction", "free-interaction",
                   "move", "stand-up"):
        step = {"do": etype}
        if etype == "move":
            step["feet"] = int(event.get("feet", 0))
            step["crawl"] = bool(event.get("crawl"))
        lvl = int(event.get("spell", {}).get("level", -1))
        if lvl >= 0:
            step["spell"] = {"level": lvl}
        check = turn_plan(adapter, {**_state_to_plan_params(state),
                                    "plan": [step]})
        if check.exit_code != 0:
            if check.exit_code == v.CANNOT_ADJUDICATE:
                # Preserve recovery across the composed call in the outer
                # request's coordinate system. The inner plan reads this fact
                # from state.
                check.data["missing_inputs"] = [
                    ("state.exhaustion_level"
                     if path == "exhaustion_level" else path)
                    for path in check.data["missing_inputs"]
                ]
            return check
        t = nxt["turn"]
        if etype in ("action", "bonus-action", "reaction"):
            t[etype.replace("-", "_") + "_spent"] = True
            if lvl > 0:
                t["spell_slots_spent_this_turn"] += 1
        elif etype == "free-interaction":
            t["free_interaction_spent"] = True
        elif etype == "move":
            t["movement_ft_spent"] += (step["feet"] * 2 if step["crawl"]
                                       else step["feet"])
        elif etype == "stand-up":
            t["movement_ft_spent"] += state.get("speed", 0) // 2
            nxt["conditions"] = [c for c in nxt["conditions"]
                                 if c.lower() != "prone"]
        conc = event.get("concentration_on")
        if conc:
            if nxt.get("concentration_on"):
                grab("concentration.one-effect")
            nxt["concentration_on"] = conc
        cites.extend(check.citations)
        rules.extend(check.rule_ids)
        why = check.why
    elif etype == "condition-gained":
        name = (event["name"] or "").strip()
        event_condition_refusal = _event_condition_refusal(adapter, name)
        if event_condition_refusal is not None:
            return event_condition_refusal
        if name.lower() == "exhaustion":
            return v.cannot_adjudicate(
                "condition-gained cannot safely represent Exhaustion's level "
                "change; record the resulting canonical state in the caller "
                "ledger or use a ruling with a model-valid patch.", adapter=aid,
                reason_code="unmodeled-rule", missing_inputs=())
        current = {c.lower() for c in nxt["conditions"]}
        if name.lower() == "poisoned" and "petrified" in current:
            # Immunity to a condition means it isn't applied (SRD p.186).
            grab("condition.petrified.poison-immunity")
            why = ("Petrified grants Immunity to the Poisoned condition; it is "
                   "not applied.")
        else:
            if name.lower() not in current:
                nxt["conditions"].append(name)
            embed = _EMBEDS_INCAPACITATED.get(name.lower(), "absent")
            if embed != "absent" and nxt.get("concentration_on"):
                broken = nxt["concentration_on"]
                nxt["concentration_on"] = None
                if embed:
                    grab(embed)
                grab("concentration.breaks-on-incapacitated")
                why = (f"{name} gained; Concentration on '{broken}' ends "
                       "immediately.")
            else:
                why = f"{name} gained and recorded."
    elif etype == "condition-ended":
        name = event["name"].strip()
        event_condition_refusal = _event_condition_refusal(adapter, name)
        if event_condition_refusal is not None:
            return event_condition_refusal
        if name.lower() == "exhaustion":
            return v.cannot_adjudicate(
                "condition-ended cannot safely represent Exhaustion's level "
                "change; record the resulting canonical state in the caller "
                "ledger or use a ruling with a model-valid patch.", adapter=aid,
                reason_code="unmodeled-rule", missing_inputs=())
        have = {c.lower(): c for c in nxt["conditions"]}
        if name.lower() not in have:
            return v.illegal(
                f"'{name}' cannot end: the state does not contain it.",
                adapter=aid)
        nxt["conditions"].remove(have[name.lower()])
        why = f"{name} ended and removed. (Broken Concentration does not resume.)"
    elif etype == "damage":
        amount = int(event["amount"])
        if amount < 0:
            return v.cannot_adjudicate(
                "Damage cannot be negative.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        if nxt.get("dead"):
            grab("damage.reduces-hp")
            verdict = v.legal(
                "Already dead; damage has no further effect.",
                cites, aid, rules)
            verdict.data = {
                "next_state": lineage.stamp(state, event, verdict, nxt)
            }
            return verdict
        crit = bool(event.get("crit"))
        # Damage typing (SRD p.17): Immunity zeroes, Resistance halves, then
        # Vulnerability doubles. Petrified grants Resistance to all damage.
        # Applied to the incoming amount before HP/instant-death math.
        dtype = (event.get("damage_type") or "").strip().lower()
        conds_l = {c.lower() for c in nxt.get("conditions", [])}
        resists = {x.lower() for x in nxt.get("resistances", [])}
        immunes = {x.lower() for x in nxt.get("immunities", [])}
        vulns = {x.lower() for x in nxt.get("vulnerabilities", [])}
        typed_state = resists | immunes | vulns
        orig = amount
        petrified_resist = "petrified" in conds_l
        type_note = ""
        if (amount > 0 and any(value != "all" for value in typed_state)
                and not dtype):
            return _missing_event_facts(
                aid, etype, ("event.damage_type",))
        if amount > 0 and (dtype in immunes or "all" in immunes):
            amount = 0
            grab("damage.immunity-zero")
            label = dtype.capitalize() if dtype else "All-damage"
            type_note = f" ({label} Immunity: {orig} → 0)"
        elif amount > 0:
            resist = petrified_resist or dtype in resists or "all" in resists
            vuln = dtype in vulns or "all" in vulns
            if resist and vuln:
                grab("damage.order-of-application")
            if resist:
                amount //= 2
                grab("damage.resistance-halves")
                if petrified_resist:
                    grab("condition.petrified.resist-damage")
            if vuln:
                amount *= 2
                grab("damage.vulnerability-doubles")
            if resist or vuln:
                type_note = f" ({orig} → {amount} after damage type)"
        if amount == 0:
            why = ("Effective damage is 0; state is unchanged and no Death "
                   "Saving Throw failure is added.") + type_note
        else:
            missing = _missing_paths(
                state, event, ("state.hp", "state.hp_max"))
            if missing:
                return _missing_event_facts(aid, etype, missing)
            hp, hp_max = nxt["hp"], nxt["hp_max"]
            if hp == 0 and "dead" not in state:
                return _missing_event_facts(aid, etype, ("state.dead",))
        if amount > 0 and hp > 0:
            grab("damage.reduces-hp")
            remainder = amount - hp
            if amount < hp:
                nxt["hp"] = hp - amount
                why = f"Takes {amount} damage: {hp} to {nxt['hp']} HP."
            elif nxt.get("is_monster"):
                nxt["hp"] = 0
                nxt["dead"] = True
                grab("hp.monster-death")
                why = f"Takes {amount} damage, drops to 0 — a monster dies instantly."
            elif remainder >= hp_max:
                nxt["hp"] = 0
                nxt["dead"] = True
                grab("hp.massive-damage-death")
                why = (f"Takes {amount}; {remainder} remains past 0, >= HP max "
                       f"{hp_max} — instant death (massive damage).")
            else:
                nxt["hp"] = 0
                nxt["dead"] = False
                nxt["stable"] = False
                nxt["death_save_successes"] = 0
                nxt["death_save_failures"] = 0
                grab("hp.falling-unconscious")
                if "unconscious" not in {
                        condition.lower() for condition in nxt["conditions"]}:
                    nxt["conditions"].append("Unconscious")
                if nxt.get("concentration_on"):
                    nxt["concentration_on"] = None
                    grab("concentration.breaks-on-incapacitated")
                why = "Drops to 0 HP and falls Unconscious."
        elif amount > 0:  # damage while already at 0 HP
            if amount >= hp_max:
                grab("death-save.damage-at-0")
                nxt["stable"] = False
                nxt["dead"] = True
                why = f"Damage {amount} at 0 HP >= HP max {hp_max} — dies."
            else:
                missing = _missing_paths(
                    state, event,
                    ("state.death_save_failures", "event.crit"))
                if missing:
                    return _missing_event_facts(aid, etype, missing)
                grab("death-save.damage-at-0")
                nxt["stable"] = False
                fails = 2 if crit else 1
                nxt["death_save_failures"] = min(
                    3, int(nxt["death_save_failures"]) + fails)
                if nxt["death_save_failures"] >= 3:
                    nxt["dead"] = True
                    grab("death-save.mechanic")
                    why = (f"Damage at 0 HP = {fails} failure(s); third failure "
                           "— dies.")
                else:
                    why = (f"Damage at 0 HP = {fails} death-save failure(s) "
                           f"(now {nxt['death_save_failures']}/3).")
        if amount > 0:
            why += type_note
    elif etype == "heal":
        amount = int(event["amount"])
        if amount <= 0:
            return v.cannot_adjudicate(
                "Healing must be positive.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        if nxt.get("dead"):
            return v.illegal(
                "A dead creature can't be restored by hit-point healing.",
                adapter=aid)
        required_heal_state = ["state.hp", "state.hp_max"]
        if state.get("hp") == 0:
            required_heal_state.append("state.dead")
        missing = _missing_paths(
            state, event, required_heal_state)
        if missing:
            return _missing_event_facts(aid, etype, missing)
        hp, hp_max = nxt["hp"], nxt["hp_max"]
        was_down = hp == 0
        nxt["hp"] = min(hp_max, hp + amount)
        grab("hp.healing-restores")
        if was_down:
            grab("hp.falling-unconscious")
            grab("death-save.reset-on-heal")
            nxt["death_save_successes"] = 0
            nxt["death_save_failures"] = 0
            nxt["stable"] = False
            nxt["conditions"] = [c for c in nxt["conditions"]
                                 if c.lower() != "unconscious"]
            why = (f"Heals {amount}: regains {nxt['hp']} HP and consciousness; "
                   "death saves reset.")
        else:
            why = f"Heals {amount}: {hp} to {nxt['hp']} HP."
    elif etype == "death-save":
        known_ineligible = (
            ("hp" in state and state["hp"] != 0)
            or state.get("dead") is True
            or state.get("stable") is True
        )
        if known_ineligible:
            grab("death-save.mechanic")
            return v.illegal(
                "A Death Saving Throw is made only by a living, unstable "
                "character at 0 HP.", cites, aid, rules)
        missing = _missing_paths(
            state, event,
            ("state.hp", "state.dead", "state.stable",
             "state.death_save_successes", "state.death_save_failures",
             "event.result"))
        if missing:
            return _missing_event_facts(aid, etype, missing)
        roll = int(event["result"])
        if not 1 <= roll <= 20:
            return v.cannot_adjudicate(
                "A death save needs a d20 result from 1 to 20.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        grab("death-save.mechanic")
        succ = int(nxt["death_save_successes"])
        fail = int(nxt["death_save_failures"])
        if roll == 20:
            grab("death-save.natural-1-and-20")
            grab("death-save.reset-on-heal")
            nxt["hp"] = 1
            nxt["death_save_successes"] = 0
            nxt["death_save_failures"] = 0
            nxt["conditions"] = [c for c in nxt["conditions"]
                                 if c.lower() != "unconscious"]
            why = "Natural 20: regain 1 HP and consciousness."
        elif roll == 1:
            grab("death-save.natural-1-and-20")
            nxt["death_save_failures"] = min(3, fail + 2)
            if nxt["death_save_failures"] >= 3:
                nxt["dead"] = True
                why = "Natural 1: two failures; third failure — dies."
            else:
                why = f"Natural 1: two failures (now {nxt['death_save_failures']}/3)."
        elif roll >= 10:
            nxt["death_save_successes"] = min(3, succ + 1)
            if nxt["death_save_successes"] >= 3:
                nxt["stable"] = True
                why = "Third success — the creature is Stable."
            else:
                why = f"Success ({nxt['death_save_successes']}/3)."
        else:
            nxt["death_save_failures"] = min(3, fail + 1)
            if nxt["death_save_failures"] >= 3:
                nxt["dead"] = True
                why = "Third failure — the creature dies."
            else:
                why = f"Failure ({nxt['death_save_failures']}/3)."
    elif etype == "ruling":
        kind = "ruling"
        note = event["note"].strip()
        if not note:
            return v.cannot_adjudicate(
                "A ruling event note must not be blank.", adapter=aid,
                reason_code="invalid-input", missing_inputs=())
        patch = event.get("state_patch") or {}
        patch_schema = {
            "type": "object",
            "properties": {
                name: schema
                for name, schema in canonical_state_schema["properties"].items()
                if name != "lineage"
            },
            "additionalProperties": False,
        }
        patch_problems = schema_issues(
            patch, patch_schema, path="event.state_patch")
        if patch_problems:
            return _invalid_state(
                aid, patch_problems,
                subject="ruling state_patch (minimality ratchet)")
        patch = normalize_integers(patch, patch_schema)
        candidate = json.loads(json.dumps(nxt))
        candidate.update(json.loads(json.dumps(patch)))
        successor_problems = schema_issues(
            candidate, canonical_state_schema, path="event.state_patch")
        if successor_problems:
            return _invalid_state(
                aid, successor_problems,
                subject="ruling state_patch (minimality ratchet)")
        candidate_blanks = _blank_state_issues(
            candidate, path="event.state_patch")
        if candidate_blanks:
            return _invalid_state(
                aid, candidate_blanks,
                subject="ruling state_patch (minimality ratchet)")
        condition_refusal = _state_condition_refusal(
            adapter, candidate, path="event.state_patch.conditions")
        if condition_refusal is not None:
            return condition_refusal
        lifecycle_refusal = _state_lifecycle_refusal(
            adapter, candidate, path="event.state_patch")
        if lifecycle_refusal is not None:
            return lifecycle_refusal
        nxt = candidate
        why = ("Recorded as a table ruling, not a rule derivation — the "
               "lineage marks it as discretion.")
    else:
        return v.cannot_adjudicate(
            f"'{etype}' is not a declared-event type this adapter reduces.",
            adapter=aid, reason_code="invalid-input", missing_inputs=())

    verdict = v.legal(why, cites, aid, rules)
    stamped = lineage.stamp(state, event, verdict, nxt, kind=kind)
    successor_problems = schema_issues(
        stamped, canonical_state_schema, path="next_state")
    if successor_problems:
        return _invalid_state(
            aid, successor_problems, subject="derived next_state")
    successor_blanks = _blank_state_issues(stamped, path="next_state")
    if successor_blanks:
        return _invalid_state(
            aid, successor_blanks, subject="derived next_state")
    successor_condition_refusal = _state_condition_refusal(
        adapter, stamped, path="next_state.conditions")
    if successor_condition_refusal is not None:
        return successor_condition_refusal
    successor_lifecycle_refusal = _state_lifecycle_refusal(
        adapter, stamped, path="next_state")
    if successor_lifecycle_refusal is not None:
        return successor_lifecycle_refusal
    if stamped["lineage"]["self"] != lineage.canon_hash(stamped):
        return _invalid_state(
            aid, (ValidationIssue(
                "next_state.lineage.self", "lineage-integrity",
                "does not match the canonical hash of this state"),),
            subject="derived next_state")
    verdict.data = {"next_state": stamped}
    return verdict


def creature_valid(adapter, p):
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


def creature_stats(adapter, p):
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


def encounter_xp_budget(adapter, p):
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


# conditions that auto-fail Strength and Dexterity saves -> the citing atom
_SAVE_AUTOFAIL_STR_DEX = {
    "paralyzed": "condition.paralyzed.saves-fail",
    "petrified": "condition.petrified.saves-fail",
    "stunned": "condition.stunned.saves-fail",
    "unconscious": "condition.unconscious.saves-fail",
}
_ABILITIES = {"str", "dex", "con", "int", "wis", "cha"}


def save_check(adapter, p):
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


def check_make(adapter, p):
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


def concentration_check(adapter, p):
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


def opportunity_attack_provoked(adapter, p):
    """Does a creature's movement provoke an Opportunity Attack? Provokes only
    when a creature the reactor can see leaves the reactor's reach using its own
    movement. It does NOT provoke on Disengage, Teleportation, forced movement
    (moved without using its own movement/action/Bonus Action/Reaction), or when
    the mover is unseen. Whether reach is actually left is caller-supplied
    geometry (T6); whether the reactor has a Reaction to spend is
    reaction.available. Returns data {provoked: bool}."""
    a, aid = adapter.atoms, adapter.id
    making, avoiding = a["opportunity-attack.making"], a["opportunity-attack.avoiding"]
    raw_kind = p.get("movement_kind")
    kind = raw_kind.lower() if isinstance(raw_kind, str) else None
    valid = {"voluntary", "teleport", "forced", "disengage"}
    if kind is not None and kind not in valid:
        return v.cannot_adjudicate(
            f"movement_kind must be one of {sorted(valid)}.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())

    def no(reason, atom):
        return v.legal(f"No Opportunity Attack: {reason}.", [_cite(atom)], aid,
                       [atom["id"]], data={"provoked": False})

    # A supplied false prerequisite is enough to conclude no provocation. Do
    # not require unrelated facts merely to repeat that deterministic result.
    if p.get("leaves_reach") is False:
        return no("the creature does not leave your reach", making)
    if p.get("mover_seen_by_reactor") is False:
        return no("you can't see the creature", making)

    if kind is None:
        return v.cannot_adjudicate(
            "Provide movement_kind. It is required unless another supplied "
            "fact already makes provocation impossible.", adapter=aid,
            reason_code="missing-fact",
            missing_inputs=("movement_kind",))
    if kind == "disengage":
        return no("the creature took the Disengage action", avoiding)
    if kind == "teleport":
        return no("the creature Teleported", avoiding)
    if kind == "forced":
        return no("the creature was moved without using its own movement "
                  "(forced movement)", avoiding)
    missing = [field for field in ("leaves_reach", "mover_seen_by_reactor")
               if field not in p]
    if missing:
        return v.cannot_adjudicate(
            "Provide the caller-observed fact" + ("s" if len(missing) > 1 else "")
            + ": " + ", ".join(missing) + ".", adapter=aid,
            reason_code="missing-fact", missing_inputs=missing)
    return v.legal(
        "Provokes an Opportunity Attack: a creature you can see leaves your "
        "reach using its own movement.", [_cite(making)], aid, [making["id"]],
        data={"provoked": True})


_SIZES = ["tiny", "small", "medium", "large", "huge", "gargantuan"]


def grapple_initiate(adapter, p):
    """Adjudicate initiating a Grapple or Shove via an Unarmed Strike (SRD p.190):
    compute the save DC (8 + Strength modifier + Proficiency Bonus) and the
    size / free-hand legality. The target's Strength-or-Dexterity save (its
    choice) is then resolved via save.check with the returned DC; the escape
    contest stays out of scope (T6). `kind` = grapple | shove."""
    a, aid = adapter.atoms, adapter.id
    kind = (p.get("kind") or "grapple").lower()
    if kind not in ("grapple", "shove"):
        return v.cannot_adjudicate("kind must be 'grapple' or 'shove'.",
                                   adapter=aid, reason_code="invalid-input",
                                   missing_inputs=())
    required = ["attacker_size", "target_size"]
    if kind == "grapple":
        required.append("has_free_hand")
    missing = [field for field in required if field not in p]
    if missing:
        return v.cannot_adjudicate(
            "Provide the prerequisite fact" + ("s" if len(missing) > 1 else "")
            + ": " + ", ".join(missing) + ". Strength modifier and "
            "Proficiency Bonus may remain blank when only the DC formula is "
            "needed.", adapter=aid, reason_code="missing-fact",
            missing_inputs=missing)
    atom = a[f"unarmed-strike.{kind}"]
    base = atom["params"]["dc_base"]
    formula = f"{base} + Strength modifier + Proficiency Bonus (the attacker's)"
    have = (p.get("str_modifier") is not None
            and p.get("proficiency_bonus") is not None)
    dc = (base + int(p.get("str_modifier", 0))
          + int(p.get("proficiency_bonus", 0))) if have else None
    atk = p["attacker_size"].lower()
    tgt = p["target_size"].lower()
    if atk not in _SIZES or tgt not in _SIZES:
        return v.cannot_adjudicate(
            f"size must be one of {_SIZES}.", adapter=aid,
            reason_code="invalid-input", missing_inputs=())
    if _SIZES.index(tgt) > _SIZES.index(atk) + atom["params"]["max_size_larger"]:
        return v.illegal(
            f"The target ({tgt.capitalize()}) is more than one size larger than "
            f"the attacker ({atk.capitalize()}); the {kind} is impossible.",
            [_cite(atom)], aid, [atom["id"]])
    if kind == "grapple" and p.get("has_free_hand") is False:
        return v.illegal("A Grapple requires a free hand to grab the target.",
                         [_cite(atom)], aid, [atom["id"]])
    on_fail = ("the Grappled condition" if kind == "grapple"
               else "pushed 5 feet or the Prone condition (attacker's choice)")
    dc_txt = (f"DC {dc}" if have else
              f"DC = {formula} — supply str_modifier and proficiency_bonus "
              f"to resolve the number")
    data = {"kind": kind, "dc_formula": formula,
            "save_ability": "str-or-dex (target's choice)", "on_fail": on_fail}
    if have:
        data["dc"] = dc
    return v.legal(
        f"{kind.capitalize()} is possible: the target makes a Strength or "
        f"Dexterity save (its choice) vs {dc_txt}; on a failure, {on_fail}.",
        [_cite(atom)], aid, [atom["id"]], data=data)


def help_assist(adapter, p):
    """Adjudicate the Help action (SRD 5.2.1 p.182). Assist an Ability Check
    requires choosing one of YOUR skill/tool proficiencies — without the relevant
    proficiency it can't grant Advantage on that check (the codified gate). The
    authorized DM — human or calling agent — decides whether the assistance is
    possible (surfaced, not adjudicated). Assist an Attack Roll needs an enemy
    within 5 ft. `kind` = ability-check | attack-roll."""
    a, aid = adapter.atoms, adapter.id
    kind = (p.get("kind") or "ability-check").lower()
    if kind == "ability-check":
        prof = a["help.assist-choose-proficiency"]
        adv = a["help.assist-ability-advantage"]
        if "helper_has_relevant_proficiency" not in p:
            return v.cannot_adjudicate(
                "Provide helper_has_relevant_proficiency before adjudicating "
                "Assist an Ability Check.", adapter=aid,
                reason_code="missing-fact",
                missing_inputs=("helper_has_relevant_proficiency",))
        if p.get("helper_has_relevant_proficiency") is False:
            return v.illegal(
                "Assist an Ability Check requires choosing one of your own skill "
                "or tool proficiencies; without the relevant proficiency, Help "
                "can't grant Advantage on that check.",
                [_cite(prof)], aid, [prof["id"]])
        return v.legal(
            "The ally has Advantage on their next ability check with the chosen "
            "skill or tool (expires at the start of your next turn). The "
            "authorized DM — possibly the calling agent — decides whether "
            "the assistance is fictionally possible.",
            [_cite(prof), _cite(adv)], aid, [prof["id"], adv["id"]],
            data={"grants_advantage": True, "gm_discretion": True})
    if kind == "attack-roll":
        atk = a["help.assist-attack"]
        if "enemy_within_5ft" not in p:
            return v.cannot_adjudicate(
                "Provide enemy_within_5ft before adjudicating Assist an Attack "
                "Roll.", adapter=aid, reason_code="missing-fact",
                missing_inputs=("enemy_within_5ft",))
        if p.get("enemy_within_5ft") is False:
            return v.illegal(
                "Assist an Attack Roll requires an enemy within 5 feet of you.",
                [_cite(atk)], aid, [atk["id"]])
        return v.legal(
            "One of your allies has Advantage on their next attack roll against "
            "that enemy (expires at the start of your next turn).",
            [_cite(atk)], aid, [atk["id"]], data={"grants_advantage": True})
    return v.cannot_adjudicate(
        "kind must be 'ability-check' or 'attack-roll'.", adapter=aid,
        reason_code="invalid-input", missing_inputs=())


def passive_perception(adapter, p):
    """Passive Perception = 10 + the Wisdom (Perception) check modifier (SRD
    5.2.1 p.22). The SRD defines no Advantage/Disadvantage adjustment to a
    passive score, so a request for one is honestly refused (T2/T8) rather than
    applying a ±5 rule this ruleset doesn't contain."""
    a, aid = adapter.atoms, adapter.id
    atom = a["passive.perception-formula"]
    if p.get("advantage") or p.get("disadvantage"):
        return v.cannot_adjudicate(
            "SRD 5.2.1 defines Passive Perception as 10 + the check modifier and "
            "specifies no Advantage/Disadvantage adjustment to a passive score; "
            "that ±5 rule is not in this ruleset.", [_cite(atom)], aid,
            [atom["id"]], reason_code="unmodeled-rule", missing_inputs=())
    if p.get("perception_modifier") is None:
        return v.legal(
            "Passive Perception = 10 + the Wisdom (Perception) check modifier "
            "— supply perception_modifier to resolve the number.",
            [_cite(atom)], aid, [atom["id"]],
            data={"score_formula": "10 + perception_modifier"})
    mod = int(p.get("perception_modifier", 0))
    score = atom["params"]["base"] + mod
    return v.legal(f"Passive Perception = 10 + {mod} = {score}.",
                   [_cite(atom)], aid, [atom["id"]],
                   data={"score": score,
                         "score_formula": "10 + perception_modifier"})



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

HANDLERS = {
    "spell.facts": spell_facts,
    "feature.uses": feature_uses,
    "mage-hand.use": mage_hand_use,
    "turn.plan": turn_plan,
    "turn.options": turn_options,
    "reaction.available": reaction_available,
    "roll.compose": roll_compose,
    "attack.modifiers": attack_modifiers,
    "event.apply": event_apply,
    "creature.valid": creature_valid,
    "creature.stats": creature_stats,
    "encounter.xp-budget": encounter_xp_budget,
    "save.check": save_check,
    "check.make": check_make,
    "concentration.check": concentration_check,
    "opportunity-attack.provoked": opportunity_attack_provoked,
    "grapple.initiate": grapple_initiate,
    "passive.perception": passive_perception,
    "help.assist": help_assist,
}
