# Anatomy of a turn

Where srdcheck sits in a game-running agent's pipeline, shown on two worked examples: a combat turn and a level-up. The pattern is the spine of the project: **deterministic rails handle everything exact, so the model's every token goes to the only work that needs a mind.**

The pipeline has three kinds of parts:

- **The model** (spends tokens): parses human intent, makes GM rulings where the rules end, chooses tactics, narrates.
- **srdcheck** (zero tokens, milliseconds): verdicts on legality with citations, enumeration of legal options, stamping state transitions.
- **Other rails** (zero tokens): the state ledger (budgets, slots, conditions, positions), geometry/line-of-sight, an auditable dice roller.

## Example 1 — a combat turn

Round 3. Kira the ranger, initiative 14. Her player says: *"I drop my bow, draw my shortsword, stab the gnoll next to me, then get behind the pillar — oh, and I kick sand in its eyes on the way."*

1. **Model parses intent** — "get behind the pillar" and "kick sand" are language, not schema. It emits a plan: drop item, draw weapon, Attack action vs Gnoll A, move 20 ft, one improvised action.
2. **Ledger answers what the transcript would answer slowly:** bonus action unspent, reaction spent last round, free object interaction available, speed 30. Without the ledger this is reconstructed from tens of thousands of tokens of table chatter — the drift zone.
3. **srdcheck rules the plan in one batched call.** Drop is free; drawing consumes the turn's free interaction; the Attack action is legal; the movement path exits Gnoll B's reach, and Gnoll B's reaction is unspent, so an opportunity attack is available to it — all as verdicts with SRD 5.2.1 citations. The sand kick returns:

```json
{
  "verdict": "cannot-adjudicate",
  "exit_code": 2,
  "citations": [],
  "why": "Improvised actions have no defined mechanic in SRD 5.2.1; outcome and cost are the GM's ruling to make.",
  "adapter": "srd-5.2.1@1.0.0"
}
```

4. **The model rules the exit-2s.** The engine didn't block the sand kick or invent a DC — it said, honestly, *this one's yours*. The model, being the GM, rules it creatively. The lawyer advised; the judge ruled; the ruling was informed rather than hallucinated.
5. **Geometry and dice do their own jobs** — cover behind the pillar is VTT math, not rules; the d20 comes from an auditable roller.
6. **srdcheck stamps the transition:** modifier and advantage/disadvantage composition from state, budgets marked spent, resulting state verified legal before the ledger commits it. Turn 300 resolves exactly like turn 3.
7. **The model narrates.** Every token it spent this turn went to understanding a human and telling the story.

On the enemy turn the rail runs the other way: srdcheck **enumerates** every legal move for each gnoll, and the model's intelligence is spent purely on choosing the one that makes the fight a story.

The economics, per turn: ~5 verdict calls and 2 ledger operations at zero tokens and single-digit milliseconds — versus thousands of hidden reasoning tokens re-deriving action economy from a transcript, with no way to prove the opportunity-attack ruling to the player who disputes it. A session is ~150 turns.

## Example 2 — a level-up (no dice, higher stakes)

A combat error lasts a round. **A character-sheet error lasts a campaign** — it silently compounds into every future roll. Build legality is where deterministic verdicts pay compound interest.

Between sessions: *"Dain (Fighter 4, Strength 16, Intelligence 10) takes his 5th level in Wizard — he's been studying that spellbook we found."*

1. **Model handles the story of it** — why Dain wants this, what it means for the character. Tokens well spent.
2. **srdcheck rules the multiclass:**

```json
{
  "verdict": "illegal",
  "exit_code": 1,
  "citations": ["SRD 5.2.1 p.24 'Character Creation > Multiclassing > Prerequisites'"],
  "why": "Multiclassing into Wizard requires Intelligence 13; Dain has 10. His current class prerequisite (Strength 13, Fighter) is met.",
  "adapter": "srd-5.2.1@1.0.0"
}
```

   Because the verdict carries the rule, the model doesn't just refuse — it narrates honestly (the arcane formulae swim before Dain's eyes) and can tell the player exactly what would have to change.
3. **The player pivots: level 5 Fighter instead.** srdcheck **enumerates** what level 5 grants and what choices are open — the legal option menu. The model advises flavor and build direction on top of a list it cannot get wrong.
4. **Arithmetic gets stamped, not trusted:** new hit point maximum from hit die + Constitution modifier, proficiency bonus check, feature grants — validated as a state transition before the sheet commits.
5. **The exit-2 moment:** the player asks to swap a fighting style for one from a homebrew document the table likes. srdcheck: `cannot-adjudicate` — unknown content, the table's call. The GM (model or human) decides, informed that they're deciding *outside* the rules rather than misinformed that it was ever inside them.

Same pipeline, no initiative order in sight: parse with intelligence, fetch from the ledger, rule with verdicts, enumerate the legal space, stamp the transition, spend the remaining tokens on the story.

## The one-line version

Everything exact refuses to be anything but exact, so everything intelligent gets to be purely intelligent.
