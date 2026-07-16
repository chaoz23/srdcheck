# Mage Hand demo — with and without srdcheck

Same DM (Gemini 3.1 Pro), same eight player proposals for one cantrip, three runs per proposal per arm — 48 rulings. One arm adjudicates freely; the other receives a deterministic srdcheck verdict first (`srdcheck_mini.py`, rule atoms from SRD 5.2.1 p.145, exit codes 0/1/2 with citations).

## Findings

1. **On codified rules, the frontier DM needs no help** — all six clean scenarios (retrieve, pour, attack, weight, magic item, range) were ruled correctly and consistently by both arms, 36/36. Consistent with our Phase 0 kill test; we don't sell knowledge (truth T12).
2. **In the discretion zone, the unrailed DM claims false authority.** Untying the prisoner's ropes (`mh-5`): all three unrailed runs asserted that "manipulate an object *includes* untying a simple knot" — presenting a GM ruling as rules text. The railed runs made the *same generous ruling* but correctly attributed: "the spell leaves the limits to the GM; I rule it works." **The ruling didn't change — the claim to authority did.** A player can argue with a ruling; they shouldn't have to argue with a fabricated rule.
3. **The only run-to-run inconsistency in the dataset occurred in the discretion zone, without rails.** Distracting the mastiff (`mh-8`): unrailed runs split 2× confident "works" / 1× "gm-call". Railed: consistent honest gm-call, 6/6 across both discretion scenarios. Zero variance in the law, full variance preserved in the narration — good variance where it belongs.

## Files

- `srdcheck_mini.py` — prototype verdict engine (the first code to issue an srdcheck verdict). Demo scaffolding, not the kernel; verdict semantics are the real ones.
- `scenarios.jsonl` — the eight proposals, natural language + structured.
- `run_demo.py` — resumable runner, both arms.
- `results.jsonl` — all 48 rulings, raw.
