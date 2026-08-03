# Anatomy of a turn

This page separates the executable product from the target architecture. The
canonical machine and human inventory is the generated
[capability map](capability-map.md).

## Executable today

srdcheck is a deterministic, capability-specific rules rail. The query metadata
and generated capability map declare each tool's scope; a caller supplies
structured facts and gets an SRD-derived verdict that applies only to that
declared scope. A `legal` result means **passes that checked scope**; it never
means that the whole action, turn, build, or scene is globally legal. Every
native verdict carries a named `coverage_level`, `checked_scope`,
`unchecked_scope`, and explicit `assumptions`; legal explanations also say
that legality applies only within the checked scope.

The usual caller is a game-running agent, often the authorized DM itself:

1. The agent-DM parses player intent and gathers table state.
2. It calls one or more relevant srdcheck tools with structured facts.
3. It branches on machine fields, not on the non-contractual `why` prose.
4. It resolves unchecked fiction, ambiguity, and table policy under its DM
   authority. A separate human DM can hold that authority too; the product does
   not assume that agent and DM are different actors.
5. It supplies any die result from an auditable roller and declares any state
   event to `event.apply`.
6. It narrates and commits state in the caller-owned ledger.

srdcheck does not parse the player's sentence, roll dice, own a campaign clock,
derive map geometry, choose tactics, or autonomously advance state.

When a call returns `cannot-adjudicate`, the agent follows the versioned
[refusal-recovery contract](refusal-recovery.md): repair invalid input, provide
named missing facts, select another adapter, use another capability, resolve a
table ruling, or stop only when no recovery is known. `resolve-table-ruling`
with `required_authority: "dm"` does not automatically mean escalation. An
authorized agent-DM exercises that authority directly; a caller without it
routes the decision to the DM. Either path records a table ruling rather than
mislabeling it as an SRD-derived result.

### Combat example: several narrow checks, not one global ruling

Kira's player says: “I draw my shortsword, attack, move behind the pillar, and
kick sand in the gnoll's eyes.” The agent-DM translates the declared budget use:

```console
srdcheck query turn.plan '{"speed":30,"plan":[{"do":"free-interaction"},{"do":"action"},{"do":"move","feet":20}]}'
```

If this returns `legal`, the plan passes the modeled action-economy and movement
budget only. It does not prove that Kira owns the weapon, can reach the target,
has line of sight, receives cover, or has a feature supporting every declared
action. The caller supplies geometry to a separate provocation check:

```console
srdcheck query opportunity-attack.provoked '{"movement_kind":"voluntary","mover_seen_by_reactor":true,"leaves_reach":true}'
```

That result answers provocation from those facts. `reaction.available` answers
the reactor's modeled budget separately. The sand kick has no shipped dedicated
query; the authorized agent-DM may rule on it directly and can record the
decision with a caller-declared `ruling` event. That is table authority, not an
SRD-derived rule result.

`turn.options` enumerates remaining **budget option kinds** such as action,
reaction, interaction, and movement. It does not enumerate creature-specific
moves, targets, spells, destinations, or tactics.

### Skill-scene example: compose shipped primitives honestly

The current engine has generic `check.make` and `passive.perception` tools. They
can resolve a caller-chosen DC, a caller-supplied roll, modeled condition
modifiers, and the passive formula. They do not implement the Hide action,
derive lighting or cover from a map, enumerate hiding locations, adjudicate
jumps, or arm Hide end triggers.

An agent-DM can still run an infiltration scene: it owns the fiction and map,
chooses or rules on facts within its authority, calls the narrow arithmetic and
condition tools that apply, and labels its table ruling separately from the
SRD-derived results. The tool must not be credited with those caller decisions.

### Mage Hand example: the shipped boundary in one spell

`mage-hand.use` implements the spell's listed uses and prohibitions, its
10-pound limit, and the supplied proposal distance. For example:

```console
srdcheck query mage-hand.use '{"kind":"attack"}'
srdcheck query mage-hand.use '{"kind":"stow_retrieve_open","weight_lb":1,"distance_ft":20}'
```

The first is illegal in the checked scope; the second passes the checked scope.
An unlisted use such as untying a knot returns `cannot-adjudicate`, leaving the
authorized agent-DM or human DM to exercise table authority.

`spell.facts` reports that Mage Hand lasts one minute and does not require
Concentration. It does not arm a duration timer, monitor the hand's future
distance, or end the spell automatically. Those are target orchestration
capabilities, not current behavior.

## Target architecture — not shipped

The product direction is a pipeline in which deterministic rails handle more of
the exact work while the agent-DM spends attention on intent, judgment, tactics,
and story. The following examples are roadmap intent:

- one batched call that decomposes and adjudicates a natural-language turn;
- feature-aware enumeration of every legal action for a specific creature;
- map-derived light, line of sight, cover, reach, and destinations;
- full Hide and jump adjudication;
- stateful duration and end-trigger orchestration; and
- character-build and level-up legality.

Until a target appears in the generated map's **shipped** section with an
executable query and test evidence, it must not be presented as current product
behavior.
