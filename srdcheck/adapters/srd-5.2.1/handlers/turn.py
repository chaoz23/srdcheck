"""Turn economy: what a creature may still do this turn, and how far.

Owns: turn.plan, turn.options, reaction.available
"""

from srdcheck import verdict as v
from srdcheck.schema import (issues as schema_issues, normalize_integers)
from .common import _MODELED_CONDITIONS, _SPEED_ZERO, _cite, _expand_conditions

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
