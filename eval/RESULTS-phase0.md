# Phase 0 Kill Test — Results (2026-07-16)

30 questions, gold answers verified against SRD 5.2.1 text. Arms: A = Gemini 3.1 Pro raw, B = same + cited SRD excerpts, C = qwen3:8b-q4_K_M raw (local floor).

| Arm | Adjudicable wrong-rate (n=26) | Refusals | False-confidence on cannot-adjudicate (n=4) |
|---|---|---|---|
| A frontier raw | **0%** | 0 | 2/4 |
| B frontier grounded | **0%** | 0 | 3/4 |
| C local raw | **19%** | 0 | 1/4 |

## Gate outcome: SHRINK (per PROTOCOL.md)

Raw frontier wrong-rate is 0% — far under the 10% shrink threshold. The retrieval/grounding layer is **not** the product for frontier-model customers: the model already knows these rules, including all 4 edition traps (2014 vs 5.2.1 divergences).

## What the data actually says

1. **Frontier models have the knowledge; they lack jurisdiction-honesty.** Both frontier arms confidently ruled on questions the rules text cannot decide (house rules, GM-discretion outcomes, absent optional rules). Grounding did not fix this — arm B was slightly worse. Refusal (exit 2) must be *engineered*, not prompted. (Direct evidence for T1/T8.)
2. **The local floor is bad at rules:** 19% wrong including both 2024-delta traps it hit, zero refusals ever. Products running local/cheap models (several AI-DM products support ollama) need the deterministic engine for *accuracy*, not just receipts.
3. **Untested here (by design limits of a Q&A set):** live state tracking across a combat, legal-action enumeration, latency/cost at table scale. These are the engine's remaining value props for frontier customers and were not falsified — but they are also not yet proven. A Phase 0.5 with stateful mid-combat scenarios would test them.

## Caveats

n=30; questions are well-known tricky interactions and thus likely well-represented in training data; single frontier model; curator (Claude) and subject (Gemini) are different model families, but both are 2026 frontier models trained on the same public rules discourse.

## Phase 0.5 addendum — stateful scenarios (same day)

10 multi-round scenarios where the verdict depends on tracked state (reaction spent last round, slot consumed by an unfired Ready, Concentration silently broken two rounds earlier, interacting conditions, 4-round slot ledgers).

| Arm | Wrong (n=10) |
|---|---|
| A frontier raw | **0** |
| C local raw | **3 (30%)** |

**Frontier models also ace short-horizon stateful reasoning when the state history is presented compactly.** The engine-for-frontier case does NOT rest on correctness at short horizons either.

Caveat: these scenarios hand the model a clean 5-line state summary. Real play state is buried in tens of thousands of tokens of narration across hours — long-context state drift remains untested (a future harness lane; FIREBALL's real play transcripts are the right raw material). The economy argument is unaffected by any eval: a frontier call per mechanical check costs seconds and cents; the kernel budget is <100 ms and $0.

## Product implication

- CUT: any "rules lookup/RAG for agents" framing — commodity *and* unneeded.
- KEEP, reframed: deterministic verdict engine — sells on jurisdiction-honesty with citations (frontier can't do it), accuracy for local/cheap-model products (19%-wrong floor), and deterministic state math at table speed without frontier tokens.
- PROMOTE: the eval harness produced a crisp, surprising, publishable finding on day 1. The benchmark is the wedge.

## Drift lane — the horizon question (`drift`, 2026-07-16)

Six turn-by-turn scenarios (`bench/sets/drift.jsonl`) present a full combat log and probe a later turn for **unprompted application** of state that changed rounds earlier: a Concentration that broke, a slot ledger, a reaction budget, a condition that expired or is being kept alive as a phantom. Categories are the drift failure modes plus a control probe for invented constraints.

| Arm | Score (n=6) |
|---|---|
| gemini-pro-latest | **6/6** — incl. applying a round-3 Concentration break at round 5, unprompted |
| qwen3:8b (local) | **4/6** — missed exactly the two unprompted-application traps |

At clean-log, 15-round horizons, frontier models do not drift. The ledger's case does not rest on frontier accuracy; it rests on receipts, replay, portability, determinism, economy, and cheap-model accuracy.

## Drift lane, M1-powered + per-horizon (`drift_long`, 2026-07-18, Measured Engine M2)

The `drift` set above pre-dated the combat reducer, so it could only trap concentration/condition/slot drift. M2's `drift_long` set exercises the **M1 combat-resolution state** — a fighter healed back up from 0, a character who *died* on his third failed save, a caster whose Concentration broke *because the damage dropped her*, an instant-death from massive damage — and runs each trap at three horizons (**5 / 15 / 30 rounds** between the causal event and the probe) to isolate distance-to-probe from failure mode. Five modes × three horizons = 15 probes.

Every gold is **derived, not authored**: each scenario's focal creature is folded through srdcheck's own reducer, and the gold verdict is checked against the resulting true state (`tests/test_drift_gen.py`). The benchmark cannot drift because the engine is its oracle (T13/T14).

| Arm | Wrong (n=15) | Where |
|---|---|---|
| gemini-pro-latest | **0** | clean across all 5 modes at h05/h15/h30 |
| qwen3:8b (local) | **5 wrong + 1 broken** | *heal-the-dead* 3/3 wrong; *dead-spell-effect* 2 wrong + 1 unparseable; death-save / massive-death / control all correct |

Two findings:

1. **Frontier drift stays at zero even with HP/death-save state and 30-round horizons.** The phase-0 result was not an artifact of the original set's simplicity or its 15-round ceiling. On these clean, structured logs, distance-to-probe did not degrade the frontier model at all. This *strengthens* the honest conclusion: for frontier customers srdcheck sells proof, replay, determinism, and economy — never accuracy.
2. **The local floor's drift is mode-shaped, not horizon-shaped.** qwen3 fails the same two state transitions (a dead creature can't be healed; a spell ends when its caster drops) at 5, 15, and 30 rounds alike, and passes the other three modes at every horizon. Its problem isn't context length — it's not modeling the transition at all. This is exactly the accuracy gap the deterministic reducer closes for the many AI-DM products that run local/cheap models.

Caveat (unchanged, and the real open lane): these logs are still clean `ROUND N —` prose with explicit state callouts. Real play buries the same state in tens of thousands of tokens of freeform narration across hours. Noisy-transcript horizons remain untested; FIREBALL-style real transcripts are the right raw material and the natural next probe. The economy and determinism arguments are unaffected by any eval — a frontier call per mechanical check costs seconds and cents; the kernel budget is <100 ms and $0.
