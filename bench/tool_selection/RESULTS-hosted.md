# MCP tool-selection study: hosted-cohort results

Status: provisional architecture decision. The preregistered frontier and
mid-tier hosted cohorts are complete; the required local cohort and native MCP
client replication are not. These results cannot authorize deprecation.

The frozen preregistration is commit `1051583ccdf819596df9f4684efc5aa1c4b0f540`.
All 224 records use case-set SHA-256
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

Across replicates, exact first-call success was 37/48 specialized versus 2/48
compact for the frontier cohort, and 36/48 versus 2/48 for mid-tier. More
importantly, the forgiving execution measure was 47/48 specialized in both
cohorts versus 6/48 and 5/48 compact. The compact arm selected `evaluate` or
`enumerate` correctly on every common case, then invented parameter names and
object shapes because the generic `params` object carried no mechanic schema.

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

The compact `capabilities` and `explain` operations were clean. This lane is
reported separately: adding missing discovery/source capabilities is not
evidence that generic mechanic execution is safe.

## Catalog cost

The specialized catalog is 23 tools and 49,350 UTF-8 bytes. The virtual compact
catalog is four tools and 1,331 bytes: 82.6% fewer tool names and 97.3% fewer
catalog bytes. The study shows where those bytes went: the removed schemas were
the information agents needed to construct executable calls.

## Provisional decision

Reject replacing specialized mechanic tools with an untyped generic
`evaluate/enumerate` surface. It fails the preregistered non-inferiority gate in
both completed cohorts by a very large margin. Preserve specialized schemas.

Investigate a hybrid only after the local cohort:

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

## Remaining evidence

Run both arms, two replicates, on one realistically deployable local AI-DM
model. Then replicate the surviving hybrid in a native MCP client and one real
Discord AI-DM integration. Until then issue #32 remains open and confidence is:

- high (0.95) that generic untyped execution should not replace specialized
  schemas for hosted agents;
- medium (0.75) that one discovery/explain gateway is worth its default-catalog
  slot;
- unavailable for local-model non-inferiority and real-table repair latency.
