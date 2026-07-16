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
