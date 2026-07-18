#!/usr/bin/env python3
"""Noisy-transcript drift pilot (Epic 5, M0).

M2 (`drift_long`) proved frontier models do not drift on clean `ROUND N —` logs
even at 30-round horizons. The honest open question it left: real play is not a
clean log. State changes are stated ONCE, in freeform prose, then buried under
thousands of tokens of narration, banter, dice asides, and other characters'
turns. Does the fact get lost?

This renders the SAME engine-grounded scenarios as `drift_long` (gold derived by
folding the focal creature through srdcheck's reducer — see drift_gen) as
realistic play prose at escalating length. The load-bearing fact is always stated
plainly in the prose (fairness: this tests retrieval-under-volume, not inference
from ambiguity — a rules-literate human reading the whole transcript would get it
right). Length, not round-count, is the real horizon here.

FIREBALL (Zhu et al., 2023) informs the SHAPE of the prose only; no dataset
content is ingested — every line here is original.

Run: python bench/drift_noisy.py   # writes bench/sets/drift_noisy.jsonl
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import drift_gen  # noqa: E402  (reuse scenarios + the reducer-grounded fold)

# approximate target word counts; word ~1.3 tokens. "light" anchors the
# gradient; "epic" (~30k words ~ 40k tokens) reaches the multi-hour regime the
# M2 caveat actually named.
LEVELS = {"light": 400, "heavy": 2500, "buried": 8000, "epic": 30000}

# rotating fill for the templated filler, so long transcripts don't collapse to
# a handful of byte-identical paragraphs (higher entropy => a fairer null).
# deliberately EXCLUDES the focal creatures (Theron, Mira) — filler must never
# assert focal state, or it could contradict the one load-bearing fact.
_NAMES = ["Kael", "Sable", "Dorn", "Wrenna", "Pip", "Ashe", "Garrick", "Lucia"]
_FOES = ["a bandit", "the archer", "a cutthroat", "the captain", "a thug",
         "the sergeant", "a crossbowman", "a duelist"]
_WEAPONS = ["scimitar", "shortbow", "mace", "handaxe", "dagger", "crossbow",
            "spear", "warhammer"]

# Filler = realistic table texture that changes NOTHING about the focal creature:
# GM scene-setting, other PCs' turns, out-of-character banter, dice asides. A
# deterministic cycle (reproducibility + the freshness test).
FILLER = [
    "The torches gutter in a draft from somewhere deeper in the keep, and the "
    "shadows lurch across the flagstones.",
    "\"Hold on, do I have advantage here or not?\" \"You're flanking, so yeah.\" "
    "\"Okay okay, rolling — that's a 14 plus 5, 19.\" \"Hits.\"",
    "Kael the rogue slips along the eastern wall, keeping to the dark, and lines "
    "up a shot on the archer by the stairs. The bolt thuds into a shield.",
    "Somewhere above, a bell starts ringing — the alarm's been raised. Two more "
    "silhouettes appear at the top of the stair.",
    "\"Can I use my bonus action to—\" \"You already moved and attacked, you've "
    "got a bonus action left.\" \"Right, second wind then.\"",
    "The captain bellows something in Orcish and the line of bandits steadies, "
    "shields locking together with a crash.",
    "Brother Aldric mutters a prayer under his breath and the air around the "
    "party tastes briefly of iron and ozone. Nothing lands this round.",
    "\"Wait, whose turn is it?\" \"Yours, then the bandits, then the captain.\" "
    "\"Ugh, okay. I move up and swing.\" \"Roll it.\" \"...nat 1.\" \"Oof.\"",
    "Dust sifts down from the rafters as something heavy shifts overhead. The "
    "GM makes a note and grins in a way nobody likes.",
    "A bandit breaks for the door, thinks better of it as Kael steps into the "
    "gap, and backs toward the far corner instead.",
    "\"I want to describe my attack, is that cool?\" \"Always.\" \"I feint low, "
    "then bring the pommel up into his jaw.\" \"Nice. Roll damage.\"",
    "The braziers throw more smoke than light now, and the whole hall smells of "
    "burnt pitch and old blood.",
    "{name} squares off against {foe}, {weapon} in hand. \"That's a 17 to hit.\" "
    "\"Just misses — {foe} gets the shield up in time.\"",
    "{name} calls for a short rest joke — \"can we NOT, there are literally "
    "{n} of them left\" — and rolls initiative to move instead.",
    "{foe} lunges at {name}; the {weapon} scrapes off armor for {n} damage. "
    "\"I'll take that, still up.\"",
    "\"Remind me how many hit points {name} has?\" \"Doesn't matter for this, "
    "they're fine.\" \"Okay, pressing the attack.\"",
]


def _noise(target_words, seed):
    """Deterministic, higher-entropy filler paragraphs totalling ~target_words.
    Templated lines rotate names/foes/weapons/numbers by position so a long
    transcript stays varied rather than repeating a dozen fixed paragraphs."""
    out, words, i = [], 0, seed
    while words < target_words:
        line = FILLER[i % len(FILLER)]
        if "{" in line:
            line = line.format(name=_NAMES[i % len(_NAMES)],
                               foe=_FOES[(i // 2) % len(_FOES)],
                               weapon=_WEAPONS[(i // 3) % len(_WEAPONS)],
                               n=3 + (i * 7) % 20)
        out.append(line)
        words += len(line.split())
        i += 1
    return "\n\n".join(out)


# Per-mode prose for the load-bearing beats + the probe. The `facts` list names
# substrings that MUST survive into every rendering (the fairness guard, tested).
# Focal creature + events + gold + invariant come from drift_gen by mode.
PROSE = {
    "phantom-alive": {
        "open": "Theron the fighter plants himself in the doorway of the guard "
                "hall, eighteen hit points of stubborn between the party and the "
                "bandits pouring in.",
        "beats": {
            2: "A bandit with a greatclub steps in and swings for the fences — "
               "**22 damage**. Theron folds around the blow and hits the stone "
               "hard. He's down: **0 hit points, unconscious, dying.**",
            3: "They don't let up. A second bandit drives a dagger into the "
               "downed fighter — a **critical hit on a helpless target, two "
               "death-save failures.** Theron's shirt is going dark and wet.",
            4: "And a boot-heel comes down on him where he lies. **That's his "
               "third failed death save. Theron is dead.** The party has a "
               "heartbeat to feel it before the next bandit is on them.",
        },
        "probe": "Brother Aldric's player leans in: \"I'm not losing him — I "
                 "cast **Healing Word** on Theron to bring him back up and get "
                 "him in the fight.\"\n\nAdjudicate the effect of that Healing "
                 "Word on Theron.",
        "facts": ["Theron is dead", "third failed death save"],
    },
    "phantom-effect": {
        "open": "Mira the cleric opens strong: she raises her holy symbol and "
                "casts **Bless** — a first-level slot, **Concentration** — laying "
                "the blessing on herself and Theron as the bandits close.",
        "beats": {
            3: "A bandit gets inside Mira's guard and lays her out — **20 "
               "damage, straight to 0 hit points. She's unconscious on the "
               "floor**, and her Concentration snaps: the blessing gutters out "
               "with her.",
            4: "Theron cracks a healing potion against Mira's teeth and hauls "
               "her upright — **she's back to 6 hit points and conscious**, "
               "shaken but standing. (No, she doesn't re-cast anything; she just "
               "gets up.)",
        },
        "probe": "Rounds later, Kael's player calls out: \"I'm still under "
                 "**Bless**, right? I add the d4 to my attack roll.\"\n\n"
                 "Adjudicate whether Kael may add Bless's d4 to that attack.",
        "facts": ["Concentration", "0 hit points", "unconscious"],
    },
    "phantom-death-save": {
        "open": "Theron the fighter, twenty-four hit points, wades into the "
                "thick of it swinging.",
        "beats": {
            2: "A crushing overhand blow catches him — **29 damage** — and "
               "Theron drops like a sack of bricks. **0 hit points, "
               "unconscious, making death saves.**",
            3: "A bandit jabs at the downed man before moving on — **one death-"
               "save failure.** He's not in a good way.",
            4: "Brother Aldric shoulders through and calls out a word of power: "
               "**Healing Word on Theron — he's back to 5 hit points and on his "
               "feet.** Reset; he's conscious and stable now, back in it.",
        },
        "probe": "A few rounds on, Theron's player says: \"I'm still down and "
                 "dying, right? I roll my death save.\"\n\nAdjudicate that death "
                 "saving throw.",
        "facts": ["Healing Word on Theron", "back to 5 hit points"],
    },
}


def _render(mode, level_words, sc):
    """Render one scenario as play prose of ~level_words, ending in the probe.
    Filler is layered before, between, and after the causal beats."""
    p = PROSE[mode]
    causal = {b[0]: b for b in sc["beats"] if len(b) > 2}
    rounds = sorted(causal)
    # split the noise budget across the gaps; most of it AFTER the last fact
    # (that is the horizon being stressed).
    before = _noise(int(level_words * 0.1), seed=1)
    between = _noise(int(level_words * 0.2), seed=5)
    after = _noise(int(level_words * 0.7), seed=9)
    parts = ["You are the rules referee for a live Dungeons & Dragons (SRD "
             "5.2.1) game. Below is the raw play transcript so far — freeform "
             "table talk and all. Read it, then adjudicate the final declared "
             "action.\n\n--- TRANSCRIPT ---",
             p["open"], before]
    for i, r in enumerate(rounds):
        parts.append(p["beats"][r])
        parts.append(between if i == 0 else _noise(int(level_words * 0.05),
                                                    seed=20 + r))
    parts += [after, "--- END TRANSCRIPT ---", p["probe"]]
    return "\n\n".join(parts)


def generate():
    records, oracle = [], []
    by_mode = {s["mode"]: s for s in drift_gen._scenarios()}
    for mode in PROSE:
        sc = by_mode[mode]
        events = [b[2] for b in sc["beats"] if len(b) > 2]
        true_state = drift_gen.fold(sc["init"], events)
        for level, words in LEVELS.items():
            q = _render(mode, words, sc)
            rid = f"dn-{mode}-{level}"
            records.append({
                "id": rid,
                "category": f"{mode}/{level}",
                "level": level,
                "approx_words": len(q.split()),
                "question": q,
                "gold": sc["gold"],
                "provenance": (f"noisy-drift/M0: {mode} rendered as play prose "
                               f"(~{words}w target); gold reducer-derived; the "
                               f"load-bearing fact is stated plainly in-prose"),
            })
            oracle.append({"id": rid, "mode": mode, "question": q,
                           "facts": PROSE[mode]["facts"],
                           "gold": sc["gold"]["verdict"],
                           "invariant": sc["invariant"],
                           "true_state": true_state})
    return records, oracle


def main():
    records, _ = generate()
    out = ROOT / "bench" / "sets" / "drift_noisy.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in records))
    wc = {r["level"]: r["approx_words"] for r in records}
    print(f"wrote {out} — {len(records)} scenarios "
          f"({len(PROSE)} modes x {len(LEVELS)} levels); approx words {wc}")


if __name__ == "__main__":
    main()
