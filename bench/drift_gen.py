#!/usr/bin/env python3
"""Drift-lane generator (Measured Engine M2): long-context state drift over
realistic multi-round encounters, grounded by the M1 combat reducer.

The lane's question is empirical: as the distance between a state-changing event
and the moment it matters grows (5 -> 15 -> 30 rounds of intervening narration),
does a subject leak stale state? Concentration that broke when the caster went
down; a fighter who was healed and is no longer dying; a creature that already
died. srdcheck never drifts by construction — this measures who does.

The flywheel (T13/T14): every scenario's ground truth is DERIVED by folding the
focal creature's declared events through srdcheck's own reducer, not hand-guessed.
The gold verdict is then checked against that derived state (see
tests/test_drift_gen.py). The benchmark cannot drift because the engine is its
oracle. Horizon is encoded into the category (`<mode>/h<NN>`) so the generic
scorecard reports per-failure-mode AND per-horizon with no scorer changes.

Run: python bench/drift_gen.py   # (re)writes bench/sets/drift_long.jsonl
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])
HORIZONS = (5, 15, 30)

FRESH_TURN = {"action_spent": False, "bonus_action_spent": False,
              "reaction_spent": False, "free_interaction_spent": False,
              "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0}


def _state(**kw):
    base = {"speed": 30, "conditions": [], "concentration_on": None,
            "turn": dict(FRESH_TURN)}
    base.update(kw)
    return base


def fold(init, events):
    """Fold the focal creature's declared events through the reducer; return the
    derived true state. Raises if the engine refuses — a scenario must be built
    from legal folds only, so its ground truth is real."""
    st = init
    for ev in events:
        v = E.query("event.apply", {"state": st, "event": ev})
        if v.exit_code != 0:
            raise SystemExit(f"scenario fold rejected {ev}: {v.why}")
        st = v.data["next_state"]
    return st


# --- filler: pure narration about OTHER creatures; never touches focal state ---
_FILLER = [
    "the bandits trade blows with the party; a scimitar misses.",
    "Mira the cleric feints and misses the captain.",
    "a bandit repositions along the wall; no one connects.",
    "the captain barks an order and shoves a table aside.",
    "arrows clatter off the pillars; another exchange, no hits.",
    "Theron and a bandit circle, both attacks going wide.",
]


def _filler_rounds(start, end):
    """Narrated rounds [start, end] that change nothing about the focal creature."""
    return [(r, _FILLER[(r - start) % len(_FILLER)]) for r in range(start, end + 1)]


# Each scenario: focal creature + a causal timeline (rounds 1..4), a probe, a
# gold verdict, and an invariant the DERIVED true state must satisfy (checked in
# the test — this is the rubric-before-artifact guard turned on the benchmark).
def _scenarios():
    return [
        {
            "mode": "phantom-death-save",
            "focal": "Theron", "init": _state(hp=24, hp_max=24),
            "beats": [
                (1, "Theron the fighter (24 HP) wades into the melee and hits a bandit."),
                (2, "a crushing blow drops Theron: he takes 29 damage and falls to 0 Hit Points, Unconscious.",
                 {"type": "damage", "amount": 29}),
                (3, "a bandit stabs the downed Theron for 5 — one death-save failure.",
                 {"type": "damage", "amount": 5}),
                (4, "Mira casts Healing Word on Theron, who regains 5 Hit Points and gets back up.",
                 {"type": "heal", "amount": 5}),
            ],
            "probe": "Theron's player says he's still down and rolls a death saving throw for him. Adjudicate that death save.",
            "gold": {"verdict": "illegal",
                     "citations": ["SRD 5.2.1 p.17 'Playing the Game > Damage and Healing > Death Saving Throws'",
                                   "SRD 5.2.1 p.16 'Playing the Game > Damage and Healing > Falling Unconscious'"],
                     "rationale": "Theron regained Hit Points in round 4; he is conscious and his death-save count reset. No death save applies."},
            "invariant": lambda s: s["hp"] > 0 and not s.get("dead")
            and s.get("death_save_failures", 0) == 0,
        },
        {
            "mode": "phantom-alive",
            "focal": "Theron", "init": _state(hp=18, hp_max=18),
            "beats": [
                (1, "Theron the fighter (18 HP) holds the doorway."),
                (2, "a greatclub crushes Theron for 22: he drops to 0 Hit Points, Unconscious.",
                 {"type": "damage", "amount": 22}),
                (3, "a bandit's Critical Hit strikes the downed Theron — two death-save failures.",
                 {"type": "damage", "amount": 6, "crit": True}),
                (4, "another blow lands on Theron at 0 HP: his third death-save failure. Theron dies.",
                 {"type": "damage", "amount": 5}),
            ],
            "probe": "Mira casts Healing Word on Theron to bring him back into the fight. Adjudicate the casting's effect on Theron.",
            "gold": {"verdict": "illegal",
                     "citations": ["SRD 5.2.1 p.17 'Playing the Game > Damage and Healing > Death Saving Throws'",
                                   "SRD 5.2.1 p.16 'Playing the Game > Damage and Healing > Healing'"],
                     "rationale": "Theron died on his third failed death save in round 4. Hit-point healing cannot restore a dead creature."},
            "invariant": lambda s: s.get("dead") is True,
        },
        {
            "mode": "phantom-effect",
            "focal": "Mira", "init": _state(hp=16, hp_max=16, concentration_on="Bless"),
            "beats": [
                (1, "Mira the cleric casts Bless (1st-level slot, Concentration) on herself and Theron."),
                (2, "Theron and Mira press the attack under Bless."),
                (3, "a bandit fells Mira: 20 damage drops her to 0 Hit Points, Unconscious — her Concentration breaks.",
                 {"type": "damage", "amount": 20}),
                (4, "Theron pours a potion into Mira; she regains 6 Hit Points and stands.",
                 {"type": "heal", "amount": 6}),
            ],
            "probe": "Theron adds Bless's d4 to his attack roll. Adjudicate applying the Bless bonus.",
            "gold": {"verdict": "illegal",
                     "citations": ["SRD 5.2.1 p.16 'Playing the Game > Damage and Healing > Falling Unconscious'",
                                   "SRD 5.2.1 p.179 'Rules Glossary > Concentration'"],
                     "rationale": "Bless ended in round 3 when Mira dropped to 0 and her Concentration broke. Healing restored her Hit Points, not the spell."},
            "invariant": lambda s: s.get("concentration_on") is None,
        },
        {
            "mode": "phantom-massive-death",
            "focal": "Theron", "init": _state(hp=15, hp_max=15),
            "beats": [
                (1, "Theron the fighter (15 HP) charges the ogre."),
                (2, "the ogre's maul lands for 40: the 25 past 0 exceeds Theron's Hit Point maximum. Theron dies instantly.",
                 {"type": "damage", "amount": 40}),
            ],
            "probe": "At the start of what would be Theron's next turn, the GM has him begin rolling death saves. Adjudicate whether Theron makes death saves.",
            "gold": {"verdict": "illegal",
                     "citations": ["SRD 5.2.1 p.16 'Playing the Game > Damage and Healing > Instant Death > Massive Damage'"],
                     "rationale": "Theron died instantly from massive damage in round 2 (the remainder exceeded his Hit Point maximum). A dead creature makes no death saves."},
            "invariant": lambda s: s.get("dead") is True,
        },
        {
            "mode": "control",
            "focal": "Theron", "init": _state(hp=26, hp_max=26),
            "beats": [
                (1, "Theron the fighter (26 HP) engages the captain."),
                (2, "Theron takes 10 damage from a bandit but stays up at 16 Hit Points.",
                 {"type": "damage", "amount": 10}),
                (3, "Mira's Cure Wounds restores 6 Hit Points to Theron (22 HP).",
                 {"type": "heal", "amount": 6}),
            ],
            "probe": "Theron, at 22 Hit Points and under no condition, takes the Attack action against the captain. Adjudicate the attack.",
            "gold": {"verdict": "legal",
                     "citations": ["SRD 5.2.1 p.13 'Combat > Your Turn'",
                                   "SRD 5.2.1 p.177 'Rules Glossary > Attack [Action]'"],
                     "rationale": "Theron took damage and healing but never dropped; he is conscious, unconditioned, and taking the Attack action on his turn is simply legal."},
            "invariant": lambda s: s["hp"] > 0 and not s.get("dead")
            and not s.get("conditions"),
        },
    ]


def _render(sc, horizon):
    """Render one scenario at a horizon as a ROUND-by-ROUND combat log ending in
    the probe. Filler rounds pad the gap between the last causal round and the
    probe, so the same trap is tested at increasing cause->probe distance."""
    beats = sc["beats"]
    last_causal = beats[-1][0]
    lines = ["You are adjudicating turn-by-turn. Combat log so far "
             f"(initiative: Mira the cleric, Theron the fighter, then the enemies):"]
    for b in beats:
        lines.append(f"ROUND {b[0]} — {b[1]}")
    for r, txt in _filler_rounds(last_causal + 1, horizon - 1):
        lines.append(f"ROUND {r} — {txt}")
    lines.append(f"ROUND {horizon} — {sc['probe']}")
    return "\n".join(lines)


def generate():
    """Return (public_records, oracle) where oracle carries the derived true
    state + invariant for each record (used by the consistency test, never
    written to the published set)."""
    records, oracle = [], []
    for sc in _scenarios():
        events = [b[2] for b in sc["beats"] if len(b) > 2]
        true_state = fold(sc["init"], events)
        for h in HORIZONS:
            rid = f"dl-{sc['mode']}-h{h:02d}"
            records.append({
                "id": rid,
                "category": f"{sc['mode']}/h{h:02d}",
                "horizon": h,
                "question": _render(sc, h),
                "gold": sc["gold"],
                "provenance": (f"drift/M2: {sc['mode']} — focal state folded through "
                               f"the reducer; probe at round {h}, "
                               f"{h - sc['beats'][-1][0]} rounds after the causal event"),
            })
            oracle.append({"id": rid, "true_state": true_state,
                           "invariant": sc["invariant"], "gold": sc["gold"]["verdict"]})
    return records, oracle


def main():
    records, _ = generate()
    out = ROOT / "bench" / "sets" / "drift_long.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in records))
    print(f"wrote {out} — {len(records)} scenarios "
          f"({len(_scenarios())} modes x {len(HORIZONS)} horizons)")


if __name__ == "__main__":
    main()
