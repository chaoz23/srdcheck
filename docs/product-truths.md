# srdcheck — Core Value & Product Truths

## Core value

**When an agent needs to know what's legal at the table, there is exactly one call to make — and the answer can be trusted, or it isn't given.**

srdcheck is the trust layer between AI and the rules of the game. It converts rules adjudication from a generation problem (hallucination-prone, unverifiable) into a computation with citations. Agents get machine verdicts; the humans at the table get, in the same payload, a plain-English *why* they can check against the book.

The longer aspiration: prove that a natural-language ruleset can be compiled into verdicts agents can trust. The SRD is the **first** ruleset, not the identity.

## Product truths

**T1 — A wrong verdict is the only unforgivable bug.**
Players and agents forgive "I can't rule on that"; they never forgive confidently wrong. Wrong-verdict rate is scored separately from coverage and is never traded for it. Exit 2 is a feature.

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
The kernel contains zero game constants. All game facts live in a swappable content layer compiled from cited source text.

**T8 — Honest boundaries beat broad coverage.**
SRD-only is a feature. "Unknown content" and "GM discretion" are truthful answers, delivered proudly. Editions are never blended.

**T9 — Eval results are never a single number.**
Per-category verdicts, with wrong-rate and refusal-rate shown separately. One blended score destroys the trust the tool exists to create.

**T10 — A stranger agent can bootstrap unattended.**
Discovery to first correct verdict in minutes with no human in the loop. The bootstrap path is itself under test: a standing eval runs a fresh agent cold and measures time-to-first-verdict.

**T11 — Verdicts at table speed.**
The verdict path is deterministic computation — no LLM call, no network dependency, runs local/offline; the human-readable *why* is templated, not generated. Working budget: p95 single verdict < 100 ms, full legal-action enumeration < 500 ms on commodity hardware.

## Anti-goals

- Not a DM, not a VTT, not a character builder UI, not a campaign manager.
- Never a homebrew/community content platform.
- Never marketed as replacing the DM; marketed as making every DM — human or agent — harder to argue with.
