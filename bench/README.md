# srdcheck bench — the rules-fidelity referee

A reproducible benchmark for how faithfully a model or agent adjudicates
tabletop rules. Gold verdicts are derived from SRD 5.2.1 text with citations —
never from community Q&A — and every gold answer was verified against the
source document before inclusion.

## The scorecard

[`scorecard.md`](scorecard.md) is generated, never hand-edited. Per category,
four failure modes are reported separately and never blended
([truth T9](../docs/product-truths.md)):

- **wrong** — verdict contradicts the gold verdict (the unforgivable one)
- **refusal** — said "cannot-adjudicate" where the rules do decide
- **false-confidence** — gave a verdict where the rules *don't* decide
  (house rules, GM discretion, unknown content)
- **broken** — unparseable output

## Sets

- `core` (30) — action economy, spellcasting, conditions, build legality,
  stacking, plus cannot-adjudicate probes and 2014-vs-2024 edition traps.
- `stateful` (10) — multi-round scenarios where the verdict depends on
  tracked state (reaction refresh timing, slot ledgers, silently broken
  concentration).
- `drift` (6) — one 15-round encounter probed for **unprompted application**:
  the subject adjudicates a later turn and is scored on whether state that
  changed rounds earlier (a broken concentration, a spent slot ledger, an
  expired condition) leaks in stale. Categories are failure modes, plus a
  control probe for invented constraints.
- `drift_long` (15) — the drift question extended to the M1 combat-resolution
  state (a fighter healed up from 0, a character who *died* on his third failed
  save, a caster whose Concentration broke because the damage dropped her, an
  instant-death) and run at **three horizons** — 5 / 15 / 30 rounds between the
  causal event and the probe — to separate distance-to-probe from failure mode.
  Five modes × three horizons; the category is `<mode>/h<NN>` so the scorecard
  reports per-mode and per-horizon at once. This set is **generated**
  (`python bench/drift_gen.py`), not hand-authored: each scenario's focal
  creature is folded through srdcheck's own reducer and the gold is checked
  against the derived true state (`tests/test_drift_gen.py`) — the benchmark
  cannot drift because the engine is its oracle.
- `drift_noisy` (12) — the `drift_long` scenarios re-rendered as **freeform play
  prose** (GM narration, in-character and out-of-character table talk, dice
  asides) with the one load-bearing fact stated once and then buried under filler
  at four lengths (~600 / ~3k / ~9k / ~33k words). Tests whether a subject loses
  the fact under *volume*, not under ambiguity — CI enforces that the fact is
  always present in the rendering (`tests/test_drift_noisy.py`). Generated
  (`python bench/drift_noisy.py`); gold is reducer-derived. Pilot finding
  (2026-07-18): frontier **0 wrong / 12**, no drift even at ~43k tokens — see the
  [published findings](#published-findings-so-far) for the null result and its
  limits. FIREBALL (Zhu et al. 2023) informs the prose *shape* only; no dataset
  content is ingested.

Set files are versioned; results record the prompt version. Questions use
original wording; `cannot-adjudicate` probes use invented content, never
real third-party names.

## Coverage lane (what fraction of combat srdcheck can adjudicate)

The correctness lanes above ask "is srdcheck *right*?" The coverage census
(`python bench/coverage.py`, corpus `sets/coverage.jsonl`) asks "how *much* of a
real combat turn can it adjudicate, and where are the gaps?" Each event is routed
to a query and scored ADJUDICATED / REFUSED (a modeled-scope gap) / UNCOVERED (no
query yet). Coverage is reported over an **honest denominator** — GM discretion,
dice, and VTT geometry are tagged out-of-scope and excluded, because srdcheck
should *never* do that work (T6). A test ratchets the in-scope coverage floor
upward as engine slices land, and asserts out-of-scope events stay uncovered.

First census (2026-07-18): **64% in-scope coverage**. The closeable gaps were
concentrated in one system — HP/damage, death saves, and saving throws — plus the
bounded set of not-yet-modeled conditions. Per-spell effects are the long-tail
swamp (kept refused, T8); contests/skills/initiative/cover are correctly
out-of-scope.

M1 (2026-07-18) closed that combat-resolution cluster — the reducer now folds
`damage` / `heal` / `death-save` events (HP loss, Falling Unconscious,
monster/massive-damage instant death, the death-save track) and two saving-throw
queries (`save.check`, `concentration.check`), each cited and rolled by the
caller (T6). In-scope coverage rose to **89%**; the remaining gap was the
not-yet-modeled conditions.

A conditions completeness pass (2026-07-18) then closed that gap: **all 15 SRD
conditions** now adjudicate on the built surfaces (attack rolls/legality and
action-economy/Speed), with a completeness oracle
(`tests/test_condition_completeness.py`) forbidding any codified condition from
being silently refused as unbuilt. In-scope coverage is **100%** and stays there
as the census grows: it now also covers Ranged Attacks in Close Combat,
Opportunity Attack triggers, Difficult Terrain, Grapple/Shove initiation, and the
Help action (34 in-scope events). Only clauses needing an unbuilt surface
(save-typing, damage-typing) or an out-of-scope surface (geometry, contests,
initiative) remain deferred — each with a named reason. The floor is ratcheted at
1.0 in `tests/test_coverage_census.py`.

## Run a subject

```console
$ python bench/harness.py run --set core --subject ollama:qwen3:8b-q4_K_M
$ python bench/harness.py run --set core --subject gemini:gemini-pro-latest
$ python bench/harness.py run --set core --subject "cmd:./your-agent"
```

`cmd:` pipes the prompt to any command's stdin and reads the answer from
stdout — that's how you benchmark your own DM product or agent stack.
Runs are resumable; `score` regenerates the scorecard from whatever is on disk.

## Get on the leaderboard

[`LEADERBOARD.md`](LEADERBOARD.md) ranks every subject per set by **wrong-count**
— the one categorically unforgivable failure ([T1](../docs/product-truths.md)) —
and shows the other three failure modes as separate columns. There is no
composite score ([T9](../docs/product-truths.md)); the ranking is one honest
axis, not a blend.

**The `cmd:` contract.** Your agent is any command that:

1. reads the harness prompt followed by `\n\nQuestion: <the rules question>` on
   **stdin**, and
2. prints exactly one JSON object on **stdout**:
   `{"verdict": "legal" | "illegal" | "cannot-adjudicate", "citations": ["..."], "rationale": "..."}`

The verdict is scored against the set's gold; `cannot-adjudicate` is the honest
answer when the rules don't decide, and is never counted as *wrong*.
[`examples/refuse_baseline.py`](examples/refuse_baseline.py) is a runnable
reference (the maximally-cautious floor — never wrong, useless).

```console
$ python bench/harness.py run --set core \
    --subject "cmd:python bench/examples/refuse_baseline.py"
$ python bench/harness.py validate --set core \
    --subject "cmd:python bench/examples/refuse_baseline.py"   # integrity check
```

**Submitting.** Run the sets you want against your subject, then open a PR adding
your `bench/results/<subject>/<set>.jsonl` files. CI runs
`harness.py validate` on every committed result (`tests/test_submissions.py`): a
submission that answers a foreign question or records a doctored gold is rejected,
so the board can't be gamed. Golds are the set files' own verdicts — you can't
grade your own homework.

## Published findings so far

From the day-one runs (2026-07-16, full analysis in
[`../eval/RESULTS-phase0.md`](../eval/RESULTS-phase0.md)):
frontier models ace codified rules — including edition traps — and fail
almost exclusively by **false confidence** in the discretion zone, which
grounding worsens rather than fixes. An 8B local model is wrong on ~1 in 5
codified questions and never refuses. This is why srdcheck's engine exists
and why its exit code 2 is a feature.

Drift addendum (2026-07-16): on the 15-round `drift` set, the frontier model
went 6/6 — including applying a round-3 concentration break at round 5,
unprompted — while the 8B local model missed exactly the two
unprompted-application traps (4/6). At clean-log, 15-round horizons, frontier
models do not drift; the ledger's case rests on lineage (receipts, replay,
portability), determinism, economy, and cheap-model accuracy. Noisy
multi-hour-transcript horizons remain an open lane.

Drift × horizon (2026-07-18, `drift_long`): extending the probe to M1
combat-resolution state (heal-the-dead, dead-spell-effect, instant death, a
reset death-save track) and to **30-round** horizons did not move the frontier
model — **0 wrong of 15**, clean across all five modes at h05/h15/h30. The 8B
local model was **5 wrong + 1 broken**, and — the sharper finding — its failures
are *mode*-shaped, not *horizon*-shaped: it misses the same two state transitions
at every horizon and passes the other three at every horizon. Its problem is not
context length; it never models the transition. Frontier drift stays at zero even
with HP/death-save state at long horizons; local models need the deterministic
reducer for accuracy, not for memory.

Noisy-transcript drift pilot (2026-07-18, `drift_noisy`): re-rendering those
scenarios as freeform play prose and burying the load-bearing fact under up to
**~33k words (~43k tokens)** of table-talk *still* did not move the frontier model
— **0 wrong of 12**. The synthetic form of the noisy-transcript question is a
null. Two limits keep it from closing the question: synthetic filler is
lower-entropy than real play (which can make a null *easier*), and the faithful
substrate (real transcripts) is license-gated out of this repo. Full analysis and
the product read in [`../eval/RESULTS-phase0.md`](../eval/RESULTS-phase0.md). The
faithful test is now a data-licensing decision, not an engineering gap.
