"""The state machine: applying an event to a turn state, and committing a
proposed transition.

Owns: event.apply, transition.commit
"""
import json

from srdcheck import verdict as v
from srdcheck.schema import (ValidationIssue, issues as schema_issues, normalize_integers)
from srdcheck.transitions import (TRANSITION_SCHEMA, canonical_hash, commit_receipt, identity, proposal as transition_proposal)
from .common import _cite
from .turn import turn_plan
from srdcheck.adapter import Adapter
from srdcheck.verdict import Verdict


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
    """The packaged canonical state contract for reducer validation. Read
    once per adapter — this used to re-read and re-parse the file on every
    event.apply call. Treat the result as read-only."""
    return adapter.data("state_schema.json")["schema"]


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


def event_apply(adapter: Adapter, p: dict) -> Verdict:
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

    supplied_key = p.get("idempotency_key")
    if (supplied_key is not None
            and (not supplied_key.strip()
                 or supplied_key != supplied_key.strip())):
        return v.cannot_adjudicate(
            "idempotency_key must be nonblank and have no surrounding "
            "whitespace.", adapter=aid, reason_code="invalid-input",
            missing_inputs=())

    idempotency_key, state_precondition_hash, transition_id = identity(
        aid, state, event, supplied_key)

    def stamp_transition(verdict, next_state, transition_kind="rule"):
        stamped_state = lineage.stamp(
            state, event, verdict, next_state, kind=transition_kind,
            idempotency_key=idempotency_key,
            state_precondition_hash=state_precondition_hash,
            transition_id=transition_id,
        )
        transition = transition_proposal(
            aid, state, event, stamped_state, idempotency_key)
        return stamped_state, transition

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
            stamped, transition = stamp_transition(verdict, nxt)
            verdict.data = {"next_state": stamped, "transition": transition,
                            "state_precondition_hash": state_precondition_hash}
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
    stamped, transition = stamp_transition(verdict, nxt, kind)
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
    verdict.data = {"next_state": stamped, "transition": transition,
                    "state_precondition_hash": state_precondition_hash}
    return verdict


def transition_commit(adapter: Adapter, p: dict) -> Verdict:
    """Validate a caller-owned atomic commit or an idempotent retry."""
    from srdcheck.engine import validation_refusal

    aid = adapter.id
    outer_problems = schema_issues(
        p, adapter.query_meta["transition.commit"]["inputSchema"])
    if outer_problems:
        return validation_refusal(outer_problems, aid)
    try:
        json.dumps(p, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return v.cannot_adjudicate(
            "Commit request must contain only finite JSON values.",
            adapter=aid, reason_code="invalid-input", missing_inputs=())

    transition = p["transition"]
    problems = schema_issues(
        transition, TRANSITION_SCHEMA, path="transition")
    if problems:
        return validation_refusal(problems, aid)
    if transition["adapter"] != aid:
        return v.cannot_adjudicate(
            "Transition adapter does not match the loaded ruleset.",
            adapter=aid, reason_code="invalid-input", missing_inputs=(),
            data={"validation_errors": [
                "transition.adapter does not match the loaded adapter"]})

    state = p["state"]
    canonical_state_schema = _state_schema(adapter)
    state_problems = schema_issues(
        state, canonical_state_schema, path="state")
    if state_problems:
        return _invalid_state(aid, state_problems)
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
    from srdcheck import lineage
    if ("lineage" in state
            and state["lineage"]["self"] != lineage.canon_hash(state)):
        return _invalid_state(
            aid, (ValidationIssue(
                "state.lineage.self", "lineage-integrity",
                "does not match the canonical hash of this state"),))
    actual_hash = canonical_hash(state)
    expected_hash = transition["state_precondition_hash"]

    # A retry after the host already persisted the successor returns the same
    # semantic commit result without applying the event twice.
    if actual_hash == transition["result_hash"]:
        lineage_data = state.get("lineage") if isinstance(state, dict) else None
        retry_matches = (
            isinstance(lineage_data, dict)
            and lineage_data.get("idempotency_key") ==
                transition["idempotency_key"]
            and lineage_data.get("state_precondition_hash") == expected_hash
            and lineage_data.get("transition_id") == transition["transition_id"]
            and lineage_data.get("event") == transition["event"]
        )
        if not retry_matches:
            return v.cannot_adjudicate(
                "Result hash matches, but lineage does not prove this "
                "transition was committed.", adapter=aid,
                reason_code="invalid-input", missing_inputs=(),
                data={"validation_errors": [
                    "state.lineage does not match transition identity"]})
        return v.legal(
            "Transition commit is already present; return the idempotent "
            "result without applying the event again.", adapter=aid,
            data={"next_state": state, "transition": transition,
                  "commit": commit_receipt(transition),
                  "state_precondition_hash": expected_hash})

    if actual_hash != expected_hash:
        return v.cannot_adjudicate(
            "State changed after evaluation; do not apply this transition. "
            "Reconcile event order and evaluate it again against current state.",
            adapter=aid, reason_code="stale-state", missing_inputs=(),
            data={
                "expected_state_precondition_hash": expected_hash,
                "actual_state_hash": actual_hash,
                "idempotency_key": transition["idempotency_key"],
                "transition_id": transition["transition_id"],
                "retry": "re-evaluate the event against the current state",
                "conflict": "another transition won the state compare-and-swap",
                "reconciliation": "order events by the host's authoritative event log",
            })

    recomputed = event_apply(adapter, {
        "state": state,
        "event": transition["event"],
        "idempotency_key": transition["idempotency_key"],
    })
    if recomputed.exit_code != v.LEGAL:
        return v.cannot_adjudicate(
            "Transition can no longer be reproduced from its precondition.",
            adapter=aid, reason_code="invalid-input", missing_inputs=(),
            data={"validation_errors": [recomputed.why]})
    expected_transition = recomputed.data.get("transition")
    if expected_transition != transition:
        return v.cannot_adjudicate(
            "Transition content failed deterministic integrity verification.",
            adapter=aid, reason_code="invalid-input", missing_inputs=(),
            data={"validation_errors": [
                "transition does not match deterministic event.apply output"]})
    return v.legal(
        "Transition precondition and deterministic result verified; the host "
        "may atomically persist next_state.", recomputed.citations, aid,
        recomputed.rule_ids,
        data={"next_state": recomputed.data["next_state"],
              "transition": transition,
              "commit": commit_receipt(transition),
              "state_precondition_hash": expected_hash})
