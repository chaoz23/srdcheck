"""Query handlers for the srd-5.2.1 adapter.

Game logic lives here, in the adapter — never in the kernel (truth T7).
Handlers read their facts from rule atoms (parameters + citations); the
control flow below is the code escape hatch the adapter spec allows.
"""

import json

from srdcheck import verdict as v


def _cite(atom):
    c = atom["citation"]
    return v.Citation(f"SRD 5.2.1 p.{c['page']} '{c['section']}'",
                      c["page"], c.get("quote"))


def mage_hand_use(adapter, p):
    """p: {kind, weight_lb?, distance_ft?} — one proposed use of the hand."""
    a = adapter.atoms
    aid = adapter.id
    if p.get("weight_lb", 0) < 0 or p.get("distance_ft", 0) < 0:
        return v.cannot_adjudicate(
            "Negative weight or distance is not a valid input; cannot "
            "adjudicate.", adapter=aid)

    leash = a["mage-hand.range-leash"]
    if p.get("distance_ft", 0) > leash["params"]["max"]:
        return v.illegal(
            f"The hand vanishes beyond {leash['params']['max']} feet; the "
            f"target is {p['distance_ft']} feet away.",
            [_cite(leash)], aid, [leash["id"]])

    for atom_id in ("mage-hand.cant-attack", "mage-hand.cant-activate-magic-items"):
        atom = a[atom_id]
        if p.get("kind") == atom["params"]["use"]:
            return v.illegal(atom["citation"]["quote"] + ".",
                             [_cite(atom)], aid, [atom_id])

    carry = a["mage-hand.carry-limit"]
    if p.get("weight_lb", 0) > carry["params"]["max"]:
        return v.illegal(
            f"The hand can't carry more than {carry['params']['max']} pounds; "
            f"the object weighs {p['weight_lb']} pounds.",
            [_cite(carry)], aid, [carry["id"]])

    grants = a["mage-hand.granted-uses"]
    if p.get("kind") in grants["params"]["uses"]:
        why = [f"granted use: '{grants['params']['uses'][p['kind']]}'"]
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
        "is the GM's ruling to make.",
        [_cite(grants)], aid, [grants["id"]])


# Turn economy. Conditions whose action-economy effects this adapter version
# models. Any other condition yields exit 2 rather than a silently wrong
# verdict (T1/T8) — several unmodeled conditions (Stunned, Paralyzed, ...)
# include Incapacitated, so ignoring them would corrupt verdicts.
_MODELED_CONDITIONS = {"grappled", "prone", "incapacitated"}


def _effective_speed(adapter, p, cites, rules):
    speed = p.get("speed", 0)
    if "grappled" in p["_conds"]:
        atom = adapter.atoms["condition.grappled.speed-zero"]
        cites.append(_cite(atom))
        rules.append(atom["id"])
        return 0
    return speed


def turn_plan(adapter, p):
    """Judge a proposed own-turn plan against budgets and modeled conditions.

    params: speed, conditions[], spent{action,bonus_action,reaction,
    free_interaction,movement_ft,spell_slots_this_turn}, plan[{do,...}].
    """
    a = adapter.atoms
    aid = adapter.id
    if int(p.get("speed", 0)) < 0:
        return v.cannot_adjudicate(
            f"Speed {p.get('speed')} is not a valid Speed; cannot adjudicate.",
            adapter=aid)
    for step in p.get("plan", []):
        lvl = step.get("spell", {}).get("level")
        if lvl is not None and not 0 <= int(lvl) <= 9:
            return v.cannot_adjudicate(
                f"Spell level {lvl} is outside the SRD range (cantrip 0 to "
                "9th level); cannot adjudicate.", adapter=aid)
    conds = [c.strip() for c in p.get("conditions", [])]
    for c in conds:
        cats = adapter.lookup_entity(c)
        if not cats:
            return v.cannot_adjudicate(
                f"'{c}' is not a condition known to this ruleset; the plan "
                "cannot be adjudicated.", adapter=aid)
        if c.lower() not in _MODELED_CONDITIONS:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but its turn-economy effects are "
                "not modeled in this adapter version; refusing rather than "
                "risking a wrong verdict.", adapter=aid)
    p = dict(p)
    p["_conds"] = {c.lower() for c in conds}

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
                return v.illegal(
                    f"Step {i} ({do}): {inc['citation']['quote']}",
                    [_cite(inc)], aid, [inc["id"]])
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
                    adapter=aid)
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
            if prone and not crawl:
                pr = a["condition.prone.movement"]
                return v.illegal(
                    f"Step {i}: moving while Prone without crawling. "
                    f"{pr['citation']['quote']}",
                    [_cite(pr)], aid, [pr["id"]])
            cost = feet * 2 if crawl else feet
            if crawl:
                cr = a["movement.crawling-cost"]
                cites.append(_cite(cr))
                rules.append(cr["id"])
            mb = a["turn.movement-budget"]
            if moved + cost > speed:
                return v.illegal(
                    f"Step {i}: {feet} ft ({cost} ft of movement) exceeds the "
                    f"remaining budget ({speed - moved} of {speed} ft). "
                    f"{mb['citation']['quote']}",
                    [_cite(mb)], aid, [mb["id"]])
            moved += cost
        else:
            return v.cannot_adjudicate(
                f"Step {i}: '{do}' is not a turn component this adapter "
                "models (improvised or unknown activity — GM's call).",
                adapter=aid)

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
    conds = {c.strip().lower() for c in p.get("conditions", [])}
    if "incapacitated" in conds:
        inc = a["condition.incapacitated.inactive"]
        return v.illegal(inc["citation"]["quote"], [_cite(inc)], aid, [inc["id"]])
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
        if not adapter.lookup_entity(c):
            return v.cannot_adjudicate(
                f"'{c}' is not a condition known to this ruleset.",
                adapter=adapter.id)
        if c.lower() not in _MODELED_CONDITIONS:
            return v.cannot_adjudicate(
                f"'{c}' is known content, but its turn-economy effects are "
                "not modeled in this adapter version; refusing rather than "
                "risking a wrong verdict.", adapter=adapter.id)
    return None


def turn_options(adapter, p):
    """T5: enumerate what remains legal this turn given the same state
    shape turn.plan takes (speed, conditions, spent) — no plan."""
    gate = _condition_gate(adapter, p)
    if gate:
        return gate
    a, aid = adapter.atoms, adapter.id
    conds = {c.strip().lower() for c in p.get("conditions", [])}
    spent = dict(p.get("spent", {}))
    cites, rules, options, notes = [], [], [], []

    def add_cite(atom_id):
        atom = a[atom_id]
        cites.append(_cite(atom))
        rules.append(atom_id)

    incapacitated = "incapacitated" in conds
    if incapacitated:
        add_cite("condition.incapacitated.inactive")
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
    if "grappled" in conds:
        add_cite("condition.grappled.speed-zero")
        speed = 0
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
                   "stunned", "grappled", "incapacitated"}


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
            "creature dies at 6); cannot adjudicate.", adapter=aid)
    for side in (atk, tgt):
        for c in side.get("conditions", []):
            if not adapter.lookup_entity(c):
                return v.cannot_adjudicate(
                    f"'{c}' is not a condition known to this ruleset.",
                    adapter=aid)
            if c.lower() not in _ATTACK_MODELED:
                return v.cannot_adjudicate(
                    f"'{c}' is known content, but its attack-roll effects are "
                    "not modeled in this adapter version; refusing rather "
                    "than risking a wrong verdict.", adapter=aid)
    ac = {c.lower() for c in atk.get("conditions", [])}
    tc = {c.lower() for c in tgt.get("conditions", [])}
    dist = p.get("distance_ft", 5)
    adv, dis, cites, rules = [], [], [], []

    def hit(atom_id, side_list, label):
        atom = a[atom_id]
        side_list.append(label)
        cites.append(_cite(atom))
        rules.append(atom_id)

    if "prone" in ac:
        hit("condition.prone.attacks", dis, "attacker is Prone")
    if "blinded" in ac:
        hit("condition.blinded.attacks", dis, "attacker is Blinded")
    if "restrained" in ac:
        hit("condition.restrained.attacks", dis, "attacker is Restrained")
    if "grappled" in ac and not tgt.get("is_grappler_of_attacker"):
        hit("condition.grappled.attacks", dis,
            "attacker is Grappled, target is not the grappler")
    if "invisible" in ac:
        if tgt.get("can_see_attacker"):
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
                          ("stunned", "condition.stunned.attacks")):
        if cond in tc:
            hit(atom_id, adv, f"target is {cond.capitalize()}")
    if "invisible" in tc:
        if atk.get("can_see_target"):
            atom = a["condition.invisible.attacks"]
            return v.cannot_adjudicate(
                "The target is Invisible but the attacker can somehow see it. "
                "The condition text says the Invisible creature doesn't gain "
                "'this benefit' against a creature that can see it — whether "
                "that clause covers the Disadvantage on attacks against it is "
                "genuinely ambiguous in the rules text. GM's call.",
                [_cite(atom)], aid, [atom["id"]])
        hit("condition.invisible.attacks", dis, "target is Invisible")

    mode, dice, comp = _compose(adapter, adv, dis)
    if comp:
        cites.append(_cite(comp))
        rules.append(comp["id"])
    data = {"roll": mode, "d20s": dice,
            "advantage_sources": adv, "disadvantage_sources": dis,
            "flat_modifiers": []}
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
    return v.legal(why, cites, aid, rules, data=data)


# The reducer (Epic 2 / T14). The model declares; the ledger derives.
# Stunned/Paralyzed embed Incapacitated (cited atoms); unknown or unmodeled
# conditions refuse rather than record state we would later misjudge.
_STATE_CONDITIONS = {"grappled", "prone", "incapacitated", "invisible",
                     "blinded", "restrained", "stunned", "paralyzed"}
_EMBEDS_INCAPACITATED = {"incapacitated": None,
                         "stunned": "condition.stunned.incapacitated",
                         "paralyzed": "condition.paralyzed.incapacitated"}

_FRESH_TURN = {"action_spent": False, "bonus_action_spent": False,
               "reaction_spent": False, "free_interaction_spent": False,
               "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0}


def _state_to_plan_params(state):
    t = state.get("turn", {})
    return {"speed": state.get("speed", 0),
            "conditions": state.get("conditions", []),
            "spent": {"action": t.get("action_spent"),
                      "bonus_action": t.get("bonus_action_spent"),
                      "reaction": t.get("reaction_spent"),
                      "free_interaction": t.get("free_interaction_spent"),
                      "movement_ft": t.get("movement_ft_spent", 0),
                      "spell_slots_this_turn":
                          t.get("spell_slots_spent_this_turn", 0)}}


def event_apply(adapter, p):
    """fold(state, declared_event) -> verdict (+ data.next_state on exit 0).

    Never produces an event, never advances time on its own, never rolls.
    """
    from srdcheck import lineage
    a, aid = adapter.atoms, adapter.id
    state = p.get("state") or {}
    event = p.get("event") or {}
    etype = event.get("type")
    nxt = json.loads(json.dumps(state)) if state else {}
    nxt.setdefault("conditions", [])
    nxt.setdefault("turn", dict(_FRESH_TURN))
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
        name = event.get("name", "")
        if not adapter.lookup_entity(name):
            return v.cannot_adjudicate(
                f"'{name}' is not a condition known to this ruleset.",
                adapter=aid)
        if name.lower() not in _STATE_CONDITIONS:
            return v.cannot_adjudicate(
                f"'{name}' is known content, but its state interactions are "
                "not modeled in this adapter version; refusing rather than "
                "recording state we would later misjudge.", adapter=aid)
        if name.lower() not in {c.lower() for c in nxt["conditions"]}:
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
        name = event.get("name", "")
        have = {c.lower(): c for c in nxt["conditions"]}
        if name.lower() not in have:
            return v.illegal(
                f"'{name}' cannot end: the state does not contain it.",
                adapter=aid)
        nxt["conditions"].remove(have[name.lower()])
        why = f"{name} ended and removed. (Broken Concentration does not resume.)"
    elif etype == "ruling":
        kind = "ruling"
        patch = event.get("state_patch") or {}
        allowed = set(json.loads(
            (adapter.root / "state_schema.json").read_text()
        )["schema"]["properties"]) - {"lineage"}
        bad = set(patch) - allowed
        if bad:
            return v.cannot_adjudicate(
                f"Ruling patch touches fields outside the state schema: "
                f"{sorted(bad)} (minimality ratchet).", adapter=aid)
        nxt.update(json.loads(json.dumps(patch)))
        why = ("Recorded as a table ruling, not a rule derivation — the "
               "lineage marks it as discretion.")
    else:
        return v.cannot_adjudicate(
            f"'{etype}' is not a declared-event type this adapter reduces.",
            adapter=aid)

    verdict = v.legal(why, cites, aid, rules)
    verdict.data = {"next_state": lineage.stamp(state, event, verdict, nxt,
                                                kind=kind)}
    return verdict


def creature_valid(adapter, p):
    """Is `name` a valid SRD 5.2.1 creature? (issue #3)

    legal = a creature in 5.2.1; illegal = SRD content but not a creature
    (e.g. a spell name); cannot-adjudicate = not in the SRD at all (could be a
    2014-only name, a typo, or third-party content — this version, having only
    the 5.2.1 adapter, cannot distinguish those honestly).
    """
    name = (p.get("name") or "").strip()
    aid = adapter.id
    if not name:
        return v.cannot_adjudicate("No creature name provided.", adapter=aid)
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
        "those.", adapter=aid)


def creature_stats(adapter, p):
    """Return a creature's CR/XP with citation (issue #2). Depends on #1's data."""
    name = (p.get("name") or "").strip()
    aid = adapter.id
    rec = adapter.entity_record("creature", name)
    if not rec:
        cats = adapter.lookup_entity(name)
        why = (f"'{name}' is SRD content but not a creature; no creature stats."
               if cats else
               f"'{name}' is not a creature in SRD 5.2.1; no stats to return.")
        return v.cannot_adjudicate(why, adapter=aid)
    return v.legal(
        f"{rec['name']}: CR {rec['cr']}, XP {rec['xp']}.",
        [v.Citation(rec["citation"])], aid,
        data={"name": rec["name"], "cr": rec["cr"], "xp": rec["xp"],
              "citation": rec["citation"]})


HANDLERS = {
    "mage-hand.use": mage_hand_use,
    "turn.plan": turn_plan,
    "turn.options": turn_options,
    "reaction.available": reaction_available,
    "roll.compose": roll_compose,
    "attack.modifiers": attack_modifiers,
    "event.apply": event_apply,
    "creature.valid": creature_valid,
    "creature.stats": creature_stats,
}
