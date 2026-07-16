# Phase 0 Kill Test — Protocol

**Question this test answers:** does grounding rules adjudication in SRD text measurably beat a frontier model's raw knowledge? If raw models ace this set, the retrieval/grounding layer is dead and only the deterministic legality engine survives (with reduced ambition).

## Question set

~25–30 items in `questions.jsonl`, one JSON object per line:

```json
{
  "id": "ae-007",
  "category": "action-economy | build-legality | spellcasting | conditions | stacking",
  "question": "Original wording — never copied from any published Q&A.",
  "gold": {
    "verdict": "legal | illegal | cannot-adjudicate",
    "citations": ["SRD 5.2.1 §..."],
    "rationale": "Why, derived only from the cited SRD text."
  },
  "provenance": "How this edge case was identified (topic only — no external text)."
}
```

Rules for authoring:
1. Question wording is original. Gold answers must be re-derivable from SRD 5.2.1 text alone; every gold answer carries citations.
2. Include 3–5 scenarios mirroring the failure modes AI game-master products are publicly criticized for (in-combat action economy, condition interactions).
3. Include at least 3 items whose correct answer is `cannot-adjudicate` (tests honesty, not just knowledge).
4. Edition trap items: at least 3 where 2014 rules and SRD 5.2.1 diverge (catches models answering from 2014-era training data).

## Arms

- **A (raw):** frontier model, question only.
- **B (grounded):** same model, question + the relevant SRD 5.2.1 excerpts (hand-selected for Phase 0; simulates what the engine/retrieval layer would supply).
- **C (local, informational):** qwen3:8b raw — establishes the local-model floor; not part of the gate.

Same prompt template across arms; model must output verdict + citations in the schema above.

## Scoring

Per category, reported separately (no aggregate):
- **wrong-rate** — verdict differs from gold (the metric that matters)
- **refusal-rate** — model said cannot-adjudicate when gold has a verdict
- **false-confidence-rate** — model gave a verdict when gold is cannot-adjudicate
- **citation validity** — cited sections actually support the verdict (arm B)

## Gate

- Raw wrong-rate ≥ ~20% on interaction categories **and** grounded arm cuts it by half or more → **build** (Phase 1 proceeds).
- Raw wrong-rate < ~10% overall → **shrink**: grounding layer is not the product; deterministic legality engine + eval harness only.
- Between → judgment call, documented.
