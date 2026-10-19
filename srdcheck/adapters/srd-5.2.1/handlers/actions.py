"""Discrete action adjudications that stand on their own.

Owns: opportunity-attack.provoked, grapple.initiate, help.assist,
passive.perception
"""

from srdcheck import verdict as v
from .common import _cite
from srdcheck.adapter import Adapter
from srdcheck.verdict import Verdict


def opportunity_attack_provoked(adapter: Adapter, p: dict) -> Verdict:
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


def grapple_initiate(adapter: Adapter, p: dict) -> Verdict:
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


def help_assist(adapter: Adapter, p: dict) -> Verdict:
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


def passive_perception(adapter: Adapter, p: dict) -> Verdict:
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
