# MCP tool-selection study: results and decision

Status: all preregistered model cohorts are complete and the architecture
decision is final for this prompt-conditioned study. Native MCP-client and
real-table replication remain mandatory before any public-tool deprecation.

The frozen preregistration is commit `1051583ccdf819596df9f4684efc5aa1c4b0f540`.
All 336 scored records use case-set SHA-256
`2244f27a8dba446eff75d7373c8fc9cb88004cae5f42d49af7cceeac12ebb685`.

## Common lane (24 cases per replicate)

| cohort | arm | replicate | selection | exact arguments | execution | exact first call | broken |
|---|---|---:|---:|---:|---:|---:|---:|
| frontier (`gpt-5.6-sol`) | specialized | 1 | 24 | 18 | 24 | 18 | 0 |
| frontier (`gpt-5.6-sol`) | specialized | 2 | 23 | 19 | 23 | 19 | 0 |
| frontier (`gpt-5.6-sol`) | compact | 1 | 24 | 1 | 4 | 1 | 0 |
| frontier (`gpt-5.6-sol`) | compact | 2 | 24 | 1 | 2 | 1 | 0 |
| mid-tier (`gpt-5.6-terra`) | specialized | 1 | 23 | 17 | 23 | 17 | 0 |
| mid-tier (`gpt-5.6-terra`) | specialized | 2 | 24 | 19 | 24 | 19 | 0 |
| mid-tier (`gpt-5.6-terra`) | compact | 1 | 24 | 1 | 2 | 1 | 0 |
| mid-tier (`gpt-5.6-terra`) | compact | 2 | 24 | 1 | 3 | 1 | 0 |
| local (`qwen3:4b-instruct-2507-q4_K_M`) | specialized | 1 | 24 | 11 | 24 | 11 | 0 |
| local (`qwen3:4b-instruct-2507-q4_K_M`) | specialized | 2 | 24 | 11 | 24 | 11 | 0 |
| local (`qwen3:4b-instruct-2507-q4_K_M`) | compact | 1 | 22 | 2 | 4 | 2 | 0 |
| local (`qwen3:4b-instruct-2507-q4_K_M`) | compact | 2 | 22 | 2 | 4 | 2 | 0 |

Across replicates, exact first-call success was 37/48 specialized versus 2/48
compact for the frontier cohort, and 36/48 versus 2/48 for mid-tier. More
importantly, the forgiving execution measure was 47/48 specialized in both
cohorts versus 6/48 and 5/48 compact. The compact arm selected `evaluate` or
`enumerate` correctly on every common case, then invented parameter names and
object shapes because the generic `params` object carried no mechanic schema.

The local cohort reproduced the same mechanism: specialized exact first-call
success was 22/48 versus 4/48 compact, while execution was 48/48 versus 8/48.
Compact selection remained high at 44/48. Across all three cohorts, pooled
exact first-call success was 95/144 (66.0%) specialized versus 8/144 (5.6%)
compact; execution was 142/144 (98.6%) versus 19/144 (13.2%).

Specialized exact-argument misses mostly omitted a supplied optional fact or
expanded an omitted budget default into explicit false/zero fields. Those calls
usually still executed correctly. The one selection miss in each hosted cohort
used `table_evaluation` instead of `spell_facts`; this is evidence that the
projection wrapper's current description can compete with a mechanic tool.

## Protocol-only lane (four cases per replicate)

| cohort | arm | exact first calls / 8 |
|---|---|---:|
| frontier | specialized | 0 |
| frontier | compact | 8 |
| mid-tier | specialized | 5 |
| mid-tier | compact | 8 |
| local | specialized | 0 |
| local | compact | 8 |

The compact `capabilities` and `explain` operations were clean. This lane is
reported separately: adding missing discovery/source capabilities is not
evidence that generic mechanic execution is safe.

## Catalog cost

The specialized catalog is 23 tools and 49,350 UTF-8 bytes. The virtual compact
catalog is four tools and 1,331 bytes: 82.6% fewer tool names and 97.3% fewer
catalog bytes. The study shows where those bytes went: the removed schemas were
the information agents needed to construct executable calls.

## Local runtime and invalid-pilot handling

The local cohort used Ollama 0.32.5 on an 8 GB Apple M1 with
`qwen3:4b-instruct-2507-q4_K_M` (`0edcdef34593`) at temperature 0, a 300-token
output cap, and a 16,384-token context. The initial 4,096-token pilot was
objectively invalid: all specialized requests were approximately 11,333 tokens
and Ollama rejected them with HTTP 400 before inference. A clean restart at
16,384 tokens then produced one client timeout on `common-22` replicate 1; a
documented targeted retry preserved the substantive failure (right tool and
successful execution, wrong canonical arguments). Invalid attempts are retained
under `diagnostics/`; neither changed the frozen case set, subject, prompts,
scoring, or thresholds.

## Decision

Reject replacing specialized mechanic tools with an untyped generic
`evaluate/enumerate` surface. It fails the preregistered non-inferiority gate in
all three cohorts by a very large margin. Preserve specialized schemas.

Adopt the following bounded hybrid direction for native-client testing:

- add or expose discovery and source explanation without changing mechanic
  execution contracts;
- clarify that `table_evaluation` is a projection wrapper, not the preferred
  first tool for native verdicts;
- cap the default catalog at 24 tools for the next minor: any new mechanic must
  extend an existing schema or ship behind an opt-in profile unless another
  default tool is retired with evidence;
- keep aliases out of default discovery, accept them for the N/N-1 semantic
  window, and announce deprecation for at least one minor before removal.

The 24-tool budget reserves at most one discovery improvement above today's 23.
It is deliberately conservative until a native-client study can tell whether a
discovery gateway lets clients avoid loading the full catalog.

The preregistered per-schema preservation threshold is met by 15 schemas in at
least one cohort: `attack_modifiers`, `check_make`, `concentration_check`,
`creature_stats`, `creature_valid`, `encounter_xp_budget`, `grapple_initiate`,
`help_assist`, `jurisdiction`, `mage_hand_use`,
`opportunity_attack_provoked`, `passive_perception`, `reaction_available`,
`save_check`, and `turn_plan`. The study does not authorize removal of the four
schemas that did not clear that threshold (`feature_uses`, `roll_compose`,
`spell_facts`, and `turn_options`); their case coverage should be improved in a
future study rather than interpreting absent evidence as equivalence.

## Remaining implementation gate

Replicate the surviving hybrid in a native MCP client and one real Discord
AI-DM integration before changing default discovery or deprecating a public
tool. Confidence is:

- very high (0.99) that generic untyped execution should not replace
  specialized schemas for hosted or local AI-DMs;
- medium-high (0.80) that one discovery/explain gateway is worth its
  default-catalog slot;
- low (0.35) on real-table repair latency until the native Discord AI-DM pilot.
