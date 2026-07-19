"""The reducer + lineage (Epic 2, T14): the model declares, the ledger derives."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck import lineage  # noqa: E402
from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])
ADAPTER = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"

FRESH = {"speed": 30, "conditions": [], "concentration_on": None,
         "turn": {"action_spent": False, "bonus_action_spent": False,
                  "reaction_spent": False, "free_interaction_spent": False,
                  "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0}}


def apply(state, event):
    v = E.query("event.apply", {"state": state, "event": event})
    return v, (v.data.get("next_state") if v.exit_code == 0 else None)


def test_budget_events_derive_state():
    v, s1 = apply(FRESH, {"type": "action", "spell": {"level": 1},
                          "concentration_on": "Bless"})
    assert v.exit_code == 0
    assert s1["turn"]["action_spent"] is True
    assert s1["turn"]["spell_slots_spent_this_turn"] == 1
    assert s1["concentration_on"] == "Bless"
    v2, _ = apply(s1, {"type": "bonus-action", "spell": {"level": 1}})
    assert v2.exit_code == 1  # second slot this turn — reducer rejects
    assert "spell.one-slot-per-turn" in v2.rule_ids


def test_turn_start_refreshes():
    _, s1 = apply(FRESH, {"type": "reaction"})
    assert s1["turn"]["reaction_spent"] is True
    v, s2 = apply(s1, {"type": "turn-start"})
    assert s2["turn"]["reaction_spent"] is False
    assert "turn.one-reaction-per-round" in v.rule_ids


def test_stunned_breaks_concentration_with_citations():
    _, s1 = apply(FRESH, {"type": "action", "spell": {"level": 1},
                          "concentration_on": "Bless"})
    v, s2 = apply(s1, {"type": "condition-gained", "name": "Stunned"})
    assert s2["concentration_on"] is None
    assert "Stunned" in s2["conditions"]
    assert "condition.stunned.incapacitated" in v.rule_ids
    assert "concentration.breaks-on-incapacitated" in v.rule_ids
    _, s3 = apply(s2, {"type": "condition-ended", "name": "Stunned"})
    assert s3["concentration_on"] is None  # broken concentration stays broken


def test_unknown_condition_refused():
    # Frightened is now a modeled state; an invented condition still refuses.
    v, nxt = apply(FRESH, {"type": "condition-gained", "name": "Bewildered"})
    assert v.exit_code == 2 and nxt is None


def test_petrified_is_immune_to_the_poisoned_condition():
    petrified = {**FRESH, "conditions": ["Petrified"]}
    v, s = apply(petrified, {"type": "condition-gained", "name": "Poisoned"})
    assert v.exit_code == 0
    assert "Poisoned" not in s["conditions"]
    assert "condition.petrified.poison-immunity" in v.rule_ids


def test_petrified_embeds_incapacitated_and_breaks_concentration():
    _, s1 = apply(FRESH, {"type": "action", "spell": {"level": 1},
                          "concentration_on": "Bless"})
    v, s2 = apply(s1, {"type": "condition-gained", "name": "Petrified"})
    assert s2["concentration_on"] is None
    assert "condition.petrified.incapacitated" in v.rule_ids
    assert "concentration.breaks-on-incapacitated" in v.rule_ids


def test_ruling_is_tagged_discretion():
    v, s1 = apply(FRESH, {"type": "ruling", "note": "sand in the eyes",
                          "state_patch": {"conditions": ["Blinded"]}})
    assert s1["lineage"]["kind"] == "ruling"
    assert s1["conditions"] == ["Blinded"]
    bad, _ = apply(FRESH, {"type": "ruling",
                           "state_patch": {"hit_points": 10}})
    assert bad.exit_code == 2
    assert "minimality" in bad.why


def test_lineage_chain_and_tamper_detection():
    events = [{"type": "action", "spell": {"level": 1},
               "concentration_on": "Bless"},
              {"type": "condition-gained", "name": "Paralyzed"},
              {"type": "turn-start"},
              {"type": "condition-ended", "name": "Paralyzed"},
              {"type": "move", "feet": 20}]

    def reducer(state, ev):
        return apply(state, ev)

    ok, states = lineage.verify(FRESH, events, reducer)
    assert ok and len(states) == 6
    assert states[-1]["lineage"]["seq"] == 5
    # replay determinism: same fold, same hashes
    ok2, states2 = lineage.verify(FRESH, events, reducer)
    assert [s.get("lineage", {}).get("self") for s in states] == \
           [s.get("lineage", {}).get("self") for s in states2]
    # tamper: mutate a mid-chain state and the chain must break
    tampered = json.loads(json.dumps(states[2]))
    tampered["speed"] = 60
    v, nxt = apply(tampered, events[2])
    assert nxt["lineage"]["prev"] != states[3]["lineage"]["prev"]


def test_minimality_ratchet():
    """Every schema field maps to real atoms; every mapped atom exists."""
    doc = json.loads((ADAPTER / "state_schema.json").read_text())
    from srdcheck.adapter import Adapter
    atoms = Adapter(ADAPTER).atoms
    props = set(doc["schema"]["properties"]) - {"lineage"}
    flat = {f.split(".")[0] for f in doc["field_atoms"]}
    assert props == flat, "schema fields must equal field_atoms coverage"
    for field, atom_ids in doc["field_atoms"].items():
        assert atom_ids, field
        for aid in atom_ids:
            assert aid in atoms, f"{field}: unknown atom {aid}"


def test_reducer_agrees_with_validator():
    """A budget event is legal iff the same single-step plan is legal."""
    states = [FRESH,
              {**FRESH, "conditions": ["Prone"]},
              {**FRESH, "turn": {**FRESH["turn"], "reaction_spent": True}}]
    events = [{"type": "action"}, {"type": "reaction"},
              {"type": "move", "feet": 10},
              {"type": "move", "feet": 10, "crawl": True},
              {"type": "stand-up"}]
    for state in states:
        for ev in events:
            step = {"do": ev["type"]}
            if "feet" in ev:
                step["feet"] = ev["feet"]
                step["crawl"] = ev.get("crawl", False)
            plan_v = E.query("turn.plan", {
                "speed": state["speed"], "conditions": state["conditions"],
                "spent": {"action": state["turn"]["action_spent"],
                          "bonus_action": state["turn"]["bonus_action_spent"],
                          "reaction": state["turn"]["reaction_spent"],
                          "free_interaction":
                              state["turn"]["free_interaction_spent"],
                          "movement_ft": state["turn"]["movement_ft_spent"],
                          "spell_slots_this_turn":
                              state["turn"]["spell_slots_spent_this_turn"]},
                "plan": [step]})
            ev_v, _ = apply(state, ev)
            assert (plan_v.exit_code == 0) == (ev_v.exit_code == 0), \
                (state["conditions"], ev, plan_v.why, ev_v.why)
