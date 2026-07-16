# srdcheck — Core Value & Product Truths

## The spine

**Pave deterministic rails so intelligence is spent only where intelligence is the only thing that works.**

Attention is the game-runner's scarce resource, and bookkeeping is theft. A general model will always complete a task — the failure is never "can't," it's "did it the expensive way" because the cheap, provable path didn't exist or wasn't discoverable. srdcheck is that path for the rules of the game.

## Core value

**When an agent needs to know what's legal at the table, there is exactly one call to make — and the answer can be trusted, or it isn't given.**

srdcheck is the trust layer between AI and the rules of the game. It converts rules adjudication from a generation problem (hallucination-prone, unverifiable) into a computation with citations. Agents get machine verdicts; the humans at the table get, in the same payload, a plain-English *why* they can check against the book.

The longer aspiration: prove that a natural-language ruleset can be compiled into verdicts agents can trust. The SRD is the **first** ruleset, not the identity.

**Post-Phase-0 reframe (2026-07-16):** srdcheck does not compete with what frontier models know — Phase 0 showed they recall these rules nearly perfectly. It sells the four things no model can supply by construction: **proof** (citations), **refusal** (jurisdiction — models were false-confident on every out-of-scope category, and grounding made it worse), **determinism** (state held exactly, not attentively), and **economy** (zero tokens in the verdict path). The benchmark that revealed this is itself a product: the neutral referee for a market already arguing about rules fidelity.

## Product truths

**T1 — A wrong verdict is the only unforgivable bug.**
Players and agents forgive "I can't rule on that"; they never forgive confidently wrong. Wrong-verdict rate is scored separately from coverage and is never traded for it. Exit 2 is a feature. *(Validated Phase 0: every model tested, frontier included, preferred a confident wrong-jurisdiction verdict to a refusal — refusal must be engineered.)*

**T2 — No citation, no rule.**
Every verdict carries its chain of SRD 5.2.1 citations. A rule we cannot cite is a rule we do not have.

**T3 — Advise, never overrule the table.**
srdcheck is the rules lawyer, not the rules judge. "Rulings, not rules" survives: the DM — human or agent — may consciously overrule any verdict, and the citation chain is what makes that overruling *informed*. srdcheck is never wired as a hard constraint that blocks play.

**T4 — One payload, two audiences.**
Machine fields (verdict, exit code, rule IDs, citations) for agents; a readable why-paragraph for humans, in the same object.

**T5 — Enumeration is the product; validation is a membership check.**
"What can this creature legally do right now?" is the question that makes agents better. The engine is a legal-action enumerator first; is-this-legal falls out of it.

**T6 — Judge, never simulate.**
No dice, no narration, no turn-taking, no owned game state. State comes in with the query; a verdict goes out.

**T7 — The mechanism never knows the game.**
The kernel contains zero game constants. All game facts live in **adapters** — content packages with their own provenance manifest (source document, hash, license, attribution) that verdicts cite through. The SRD ships as adapter #1, a reference implementation, not the identity. Anyone — a community, a table, a publisher protecting its own IP — can ship an adapter for their ruleset without their content ever passing through this project.

**T8 — Honest boundaries beat broad coverage.**
SRD-only is a feature. "Unknown content" and "GM discretion" are truthful answers, delivered proudly. Editions are never blended. *(Validated Phase 0: jurisdiction-honesty is the one thing frontier models measurably lack.)*

**T9 — Eval results are never a single number.**
Per-category verdicts, with wrong-rate and refusal-rate shown separately. One blended score destroys the trust the tool exists to create.

**T10 — A stranger agent can bootstrap unattended.**
Discovery to first correct verdict in minutes with no human in the loop. The bootstrap path is itself under test: a standing eval runs a fresh agent cold and measures time-to-first-verdict.

**T11 — Verdicts at table speed.**
The verdict path is deterministic computation — no LLM call, no network dependency, runs local/offline; the human-readable *why* is templated, not generated. Working budget: p95 single verdict < 100 ms, full legal-action enumeration < 500 ms on commodity hardware.

**T12 — Never sell what the model already has.**
Knowledge parity with frontier models is assumed, not contested. Any feature whose pitch is "the model might not know this" is cut on sight. The value is proof, refusal, determinism, and economy — the four things a model cannot supply by construction.

**T13 — The benchmark is a product, not a test suite.**
The eval harness ships findings, versioned and citable by third parties; its quality bar is the product bar, and it judges srdcheck itself as readily as any model. Its first finding — frontier models ace rules knowledge and flunk jurisdiction — is the reason the rest of the product exists.

**T14 — Every state has a lineage.**
A state object is valid only as the output of a stamped transition chain, verifiable by replay. The model declares; the ledger derives: state entries are computed from declared events, never asserted — a diary is not a ledger. GM rulings enter the lineage tagged as rulings, so the chain separates law from discretion. srdcheck never produces an event, never advances time, never generates randomness — the caller owns the loop; we own the fold.

## Anti-goals

- Not a DM, not a VTT, not a character builder UI, not a campaign manager.
- Never a homebrew/community content platform — the adapter catalog *points*, it never hosts. Content lives in its maintainer's repo, under its maintainer's license.
- Never marketed as replacing the DM; marketed as making every DM — human or agent — harder to argue with.
- **Never a retrieval/RAG/lookup layer** — killed by Phase 0 data (frontier raw = 0% wrong; grounding fixed nothing and worsened false confidence).
