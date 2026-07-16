# Anatomy of a turn

Where srdcheck sits in a game-running agent's pipeline, shown on three worked examples: a combat turn, a complex skill scene, and one famously squirrely cantrip. The pattern is the spine of the project: **deterministic rails handle everything exact, so the model's every token goes to the only work that needs a mind.**

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

## Example 2 — the infiltration (a complex skill scene)

No initiative, no attack rolls — and more rules in flight than most combats. The 2024 Hide action is a precondition gate, a fixed DC, a granted *condition*, and four armed end-triggers; real tables argue about every one of those. Watch the pipeline carry it.

Night. Vex the rogue drops through a warehouse skylight onto the rafters. Two guards below, one carrying a lantern. Her player: *"I hide in the shadows above them."*

1. **Model parses intent; the light rail answers the physics.** The lantern's radius puts Vex's rafter in Dim Light — which is *Lightly* Obscured. srdcheck rules the Hide as declared:

```json
{
  "verdict": "illegal",
  "exit_code": 1,
  "citations": ["SRD 5.2.1 p.183 'Rules Glossary > Hide [Action]'",
                "SRD 5.2.1 p.11 'Exploration > Vision and Light'"],
  "why": "Hiding requires being Heavily Obscured or behind Three-Quarters or Total Cover, and out of any enemy's line of sight. Dim Light is only Lightly Obscured, and both guards have line of sight to the rafter.",
  "adapter": "srd-5.2.1@1.0.0"
}
```

   "You can't hide there" is one of the great table arguments. The citation ends it in one line, and the enumerator answers the player's next question — *then where?* — with the legal spots: behind the water tank (Total Cover from both guards).
2. **She hides for real.** Preconditions now met, the engine knows the check is DC 15 Dexterity (Stealth) — she rolls 17. The ledger commits the Invisible condition **with its four end-triggers armed**: a sound louder than a whisper, an enemy finds her, an attack roll, a spell with a Verbal component. Her 17 is recorded as the DC to find her. This is the mechanic AI DMs fumble worst — a condition whose *ending* is event-driven across future turns. In a ledger it's exact; in a context window it evaporates.
3. **A guard passes below.** Passive Perception 13 against find-DC 17 — pure rail math from the recorded state, zero tokens, and the guard walks on. The model narrates the held breath.
4. **The jump.** *"I run along the beam and leap to the next rafter — the gap's maybe 13 feet."* Vex has Strength 12. With a 10-foot run-up, a Long Jump covers **up to your Strength score in feet**: 12. Verdict: illegal, cited to p.184 — no roll, no debate, no physics argument with the GM. Enumeration again answers *what can I do:* the nearer crossbeam at 12 feet is reachable (standing jump would be 6). The model turns the constraint into drama — the scramble, the dust falling toward the lantern light.
5. **The coin.** She flips a coin across the room to pull a guard away. Does the clatter count as *her* making a sound louder than a whisper — does it break her hiding? The rules text genuinely doesn't resolve whose sound a caused noise is. srdcheck returns `cannot-adjudicate`, and the model — the judge — rules it: the distraction works, she stays hidden, but the far guard is alert now. An honest ambiguity, ruled creatively, *known* to be a ruling rather than mistaken for a rule.

Same pipeline as combat: intelligence at both ends (intent in, story out), rails in the middle — and the scene's tension came entirely from constraints the engine refused to bend.

*(Build legality is the third place the pattern pays, quietly: a combat error lasts a round, but a character-sheet error compounds into every roll for a campaign. srdcheck stamps level-ups the same way it stamps turns.)*

## Example 3 — the Mage Hand test (one cantrip, all three exit codes)

Mage Hand is the improvisation magnet of the game: a spectral floating hand, and a table full of players inventing uses for it. It's also where language models get squirrely in both directions — the over-permissive hand that strangles guards, the over-restrictive one that can't touch anything. The actual spell (SRD 5.2.1 p.145) is a short *can* list — manipulate an object, open an unlocked door or container, stow or retrieve from an open container, pour out a vial — and a short *can't* list — attack, activate magic items, carry more than 10 pounds — floating in an ocean of GM discretion. That makes it a one-object test of the entire verdict boundary. Same wizard, four proposals, thirty seconds of table time:

- *"The hand lifts the key out of the open lockbox across the room."* — **exit 0, legal**: retrieving an item from an open container, under 10 pounds, within 30 feet. All three cited.
- *"The hand grabs his dagger and stabs him."* — **exit 1, illegal**: the hand can't attack. One citation, no debate.
- *"It picks up the strongbox and floats it to me."* — **exit 1, illegal**: the strongbox weighs 25 pounds; the limit is 10. Arithmetic, cited.
- *"It unties the prisoner's ropes while I keep talking."* — **exit 2, cannot-adjudicate**: is untying knots "manipulating an object"? The text neither grants nor forbids fine manipulation; there's no check mechanic in the spell. The model rules it — maybe yes but slowly, maybe a check — knowing it's ruling, not reciting.

And two quiet ledger jobs while all that happens: the hand's 30-foot leash and 1-minute duration are armed triggers (drift past the range and it vanishes — mid-scene, whether anyone remembers or not), and when the player later asks *"does casting Web break my concentration on the hand?"* the verdict is instant and cited: Mage Hand has no Concentration requirement at all — a thing models confidently get wrong in both directions.

The squirrely spell is the sales demo: hard walls where the text draws them, honest shrugs where it doesn't, and the model free to be a good GM in exactly the space the rules left for one.

## The one-line version

Everything exact refuses to be anything but exact, so everything intelligent gets to be purely intelligent.
