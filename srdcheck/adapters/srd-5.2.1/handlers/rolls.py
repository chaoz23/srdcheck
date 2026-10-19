"""d20 composition and the attack-roll modifier stack.

Owns: roll.compose, attack.modifiers
"""

from srdcheck import verdict as v
from .common import _MODELED_CONDITIONS, _cite, _condition_category_gate, _effect_required_facts, _expand_conditions, _missing_fact_refusal, _path_present, _query_required_facts

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
