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

Set files are versioned; results record the prompt version. Questions use
original wording; `cannot-adjudicate` probes use invented content, never
real third-party names.

## Run a subject

```console
$ python bench/harness.py run --set core --subject ollama:qwen3:8b-q4_K_M
$ python bench/harness.py run --set core --subject gemini:gemini-pro-latest
$ python bench/harness.py run --set core --subject "cmd:./your-agent"
```

`cmd:` pipes the prompt to any command's stdin and reads the answer from
stdout — that's how you benchmark your own DM product or agent stack.
Runs are resumable; `score` regenerates the scorecard from whatever is on disk.

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
