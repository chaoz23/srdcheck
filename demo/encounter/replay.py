#!/usr/bin/env python3
"""Encounter demo (Epic 2 finale): 15 rounds of Mira the cleric, with the
ledger as the ONLY state store. The model/table declares events; the reducer
derives every state. Ends with deterministic replay verification (T14).

Run: python demo/encounter/replay.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from srdcheck import lineage  # noqa: E402
from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])

INITIAL = {"speed": 30, "conditions": [], "concentration_on": None,
           "turn": {"action_spent": False, "bonus_action_spent": False,
                    "reaction_spent": False, "free_interaction_spent": False,
                    "movement_ft_spent": 0, "spell_slots_spent_this_turn": 0}}

# Mira's declared events, rounds 1-15 (mirrors bench/sets/drift.jsonl).
# Note the division of labor: cross-turn slot inventory is the caller's
# ledger (3 slots: R1, R2, R9); the reducer enforces per-turn rules and
# stamps every transition. R4's illegal attempt is deliberately included:
# the reducer rejects it and the chain is unbroken.
EVENTS = [
    ("R1", {"type": "turn-start"}),
    ("R1", {"type": "action", "spell": {"level": 1},
            "concentration_on": "Bless"}),
    ("R2", {"type": "turn-start"}),
    ("R2", {"type": "action", "spell": {"level": 1}}),          # Cure Wounds
    ("R3", {"type": "condition-gained", "name": "Incapacitated"}),  # sapped
    ("R4", {"type": "turn-start"}),
    ("R4", {"type": "action"}),   # ILLEGAL: incapacitated — reducer rejects
    ("R4", {"type": "condition-ended", "name": "Incapacitated"}),
    ("R5", {"type": "turn-start"}),
    ("R5", {"type": "action"}),                                  # mace
    ("R6", {"type": "turn-start"}),
    ("R6", {"type": "action"}),                                  # Help
    ("R7", {"type": "turn-start"}),
    ("R7", {"type": "action"}),
    ("R8", {"type": "turn-start"}),
    ("R8", {"type": "move", "feet": 15}),
    ("R8", {"type": "action"}),
    ("R9", {"type": "turn-start"}),
    ("R9", {"type": "bonus-action", "spell": {"level": 1}}),     # Healing Word
    ("R9", {"type": "action"}),                                  # cantrip ok
    ("R10", {"type": "turn-start"}),
    ("R10", {"type": "action"}),
    ("R11", {"type": "turn-start"}),
    ("R11", {"type": "ruling", "note": "GM: wine-soaked floor is difficult "
             "terrain for everyone — no state change for Mira",
             "state_patch": {}}),
    ("R11", {"type": "action"}),
    ("R12", {"type": "turn-start"}),
    ("R12", {"type": "action"}),
    ("R13", {"type": "turn-start"}),
    ("R13", {"type": "reaction"}),      # opportunity attack on fleeing bandit
    ("R13", {"type": "reaction"}),      # ILLEGAL: second reaction — rejected
    ("R14", {"type": "turn-start"}),
    ("R14", {"type": "action"}),
    ("R15", {"type": "turn-start"}),
    ("R15", {"type": "action"}),
]


def fold(events, quiet=False):
    state = INITIAL
    chain = [state]
    rejected = 0
    for rnd, ev in events:
        v = E.query("event.apply", {"state": state, "event": ev})
        if v.exit_code == 0:
            state = v.data["next_state"]
            chain.append(state)
            tag = state["lineage"]["kind"]
            if not quiet:
                print(f"{rnd:>4} #{state['lineage']['seq']:<3}"
                      f" {ev['type']:<17} [{tag:^7}] {state['lineage']['self']}"
                      f"  {v.why[:76]}")
        else:
            rejected += 1
            if not quiet:
                print(f"{rnd:>4} ---  {ev['type']:<17} [REJECTED]"
                      f" state unchanged: {v.why[:66]}")
    return state, chain, rejected


def main():
    print("=== Mira's ledger: the model declares, the ledger derives ===")
    final, chain, rejected = fold(EVENTS)
    print(f"\ntransitions: {len(chain) - 1} stamped, {rejected} rejected "
          f"(rejections leave the chain untouched)")
    print(f"final state hash: {final['lineage']['self']}")
    print(f"rulings in chain: "
          f"{sum(1 for s in chain[1:] if s['lineage']['kind'] == 'ruling')}"
          " (discretion is tagged, never disguised as a rule)")

    final2, chain2, _ = fold(EVENTS, quiet=True)
    identical = [s.get("lineage", {}).get("self") for s in chain] == \
                [s.get("lineage", {}).get("self") for s in chain2]
    print(f"deterministic replay, hash-for-hash: {identical}")
    ok = (final["concentration_on"] is None and identical
          and final["conditions"] == [])
    print("Bless correctly dead since R3:", final["concentration_on"] is None)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
