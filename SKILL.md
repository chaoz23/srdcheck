---
name: srdcheck
version: 0.5.1
description: >
  Deterministic rules verdicts for D&D 5e game-running agents, cited to the
  SRD 5.2.1 (2024 rules). Use it mid-turn whenever a rules question has a
  codified answer: "can I grapple while raging?", "is this attack at
  advantage?", "does she still have her reaction?", "is Hexblade even a thing
  here?", "what's the save DC for this shove?", "is this multiclass legal?",
  "how much XP fits this encounter?". Also use it when a player cites a rule
  from memory and you want the actual text, and when you need to know whether
  content is inside the rules at all before adjudicating it.
---

# srdcheck — rules lawyer for agents

Machine adjudication of the SRD 5.2.1. Every verdict is deterministic (no
model calls, no network, no randomness), sub-millisecond, and cites verbatim
rule text. It answers what the written rules say — your table's ruling
authority stays with the DM.

## Three things to remember

1. **The exit code IS the verdict:** 0 legal · 1 illegal · 2 cannot-adjudicate.
2. **Exit 2 is a first-class honest answer, never an error.** It means the
   question is outside the loaded rulesets or genuinely up to the DM. Route it
   to a human ruling; do not retry, rephrase, or guess.
3. **Cite what it cites.** Verdicts carry verbatim SRD quotes — relay the
   citation, don't paraphrase from your own rules memory.

## Invocation

```bash
srdcheck jurisdiction "<name>"              # is this content in the rules at all?
srdcheck query <query-type> '<params-json>' # adjudicate one question
srdcheck capabilities                       # versions, adapter digests, query types
echo '{"type":"...","params":{...}}' | srdcheck --pipe
```

MCP: command `srdcheck-mcp` (stdio), same tools with `_` for `.`
(e.g. `grapple_initiate`). Input schemas: `srdcheck --schema` or tool.json.

Query types (srd-5.2.1 adapter): attack.modifiers · check.make ·
concentration.check · creature.stats · creature.valid · encounter.xp-budget ·
event.apply · feature.uses · grapple.initiate · help.assist · mage-hand.use ·
opportunity-attack.provoked · passive.perception · reaction.available ·
roll.compose · save.check · spell.facts · turn.options · turn.plan

## Worked example

A raging barbarian (Str +3, PB +2) tries to grapple a Large ogre:

```bash
srdcheck query grapple.initiate '{"kind":"grapple","str_modifier":3,"proficiency_bonus":2,"attacker_size":"medium","target_size":"large","has_free_hand":true}'
```

```json
{
  "verdict": "legal",
  "exit_code": 0,
  "why": "Grapple is possible: the target makes a Strength or Dexterity save (its choice) vs DC 13; on a failure, the Grappled condition.",
  "citations": [{
    "section": "SRD 5.2.1 p.190 'Rules Glossary > Unarmed Strike'",
    "page": 190,
    "quote": "The target must succeed on a Strength or Dexterity saving throw (it chooses which), or it has the Grappled condition. [...]"
  }],
  "rule_ids": ["unarmed-strike.grapple"],
  "adapter": "srd-5.2.1@0.2.0",
  "data": {"kind": "grapple", "dc": 13, "save_ability": "str-or-dex (target's choice)", "on_fail": "the Grappled condition"}
}
```

The same query against a Gargantuan target → exit 1, `"why": "The target
(Gargantuan) is more than one size larger than the attacker (Medium); the
grapple is impossible."` And content outside the SRD refuses honestly:

```bash
srdcheck jurisdiction "Hexblade"   # exit 2: "'Hexblade' is not present in any loaded ruleset [...]"
```

## MUST / MUST NOT

- MUST check `jurisdiction` before adjudicating content you haven't seen this
  session; unknown names produce exit 2, not a legality opinion.
- MUST treat exit 3 as a usage/internal error (fix the call), never a verdict.
- MUST pass every field the query schema allows when you have it — a missing
  optional field can demote a numeric answer to a formula (e.g. grapple DC).
- MUST NOT invoke a model to compute anything a query type answers — a model
  call where a lookup exists is a defect.
- MUST NOT present exit 2 to players as "illegal" or as a malfunction; say the
  rules don't decide this and hand it to the DM.
- MUST NOT adjudicate homebrew/third-party content by analogy; that's the
  DM's call, recorded as a ruling, not a rule.
- MUST NOT reproduce rule text beyond the citations the tool emits.

## Validation checkpoints (self-audit before relaying a verdict)

jurisdiction confirmed · schema-valid params · exit code read (not just the
JSON) · citation relayed · exit-2 routed to a human, not absorbed.

## Cross-skill workflows (check family)

- **Live ruling:** srdcheck verdict → exit 2 → DM rules → record the ruling in
  the table-kit session ledger (JSONL), tagged as ruling, not rule.
- **Character audit:** charactercheck derives the sheet; names it can't derive
  land in its exit-2 report → `srdcheck jurisdiction` each → in-SRD disputes
  adjudicated here, the rest to the DM.
- **Session retro:** dmcheck reads the table charter + session ledger;
  srdcheck verdicts referenced there give it citations to check conduct against.

Family contract (exit-code semantics, licensing, provenance): see FAMILY.md.

## Changelog / stale-knowledge deltas

- **0.5.x:** default adapter is **srd-5.2.1 (2024 rules)**; srd-5.1 (2014) is
  a non-default adapter — if you hold 2014-era rules knowledge, verify with
  `edition-check "<name>"` before trusting it. Adapter kit: `conformance`,
  `new-adapter`.
- **0.4.x → 0.5.x:** no CLI breaking changes; `capabilities` now prints
  per-adapter sha256 digests (cite `adapter@version` from verdicts when
  logging precedents).

srdcheck is unofficial; rule content solely from the SRD 5.2.1 under
CC-BY-4.0, pinned by SHA-256. Verdicts are advisory: the DM owns the table.
