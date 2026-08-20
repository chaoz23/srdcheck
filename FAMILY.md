# The check family — shared contract (v2.1)

Canonical copy: this file, in [srdcheck](https://github.com/chaoz23/srdcheck)
(the family's reference implementation). Sibling repos link here.

**What this document is.** Clauses 1–6 are **descriptive**: the family already
implements them. Clause 7 is **partly prescriptive** — it is stated per member
class, and the gaps that remain open are named in the table itself rather than
left implied. v1 claimed to be wholly descriptive while clause 7 was not yet
met by every member; v2 fixes that claim rather than quietly restating it.

## Members

Members differ by what they produce, and the contract binds them accordingly.

| Tool | Class | Verdict domain |
| :-- | :-- | :-- |
| [srdcheck](https://github.com/chaoz23/srdcheck) | verdict | Written-rules legality (SRD 5.2.1 + 5.1 adapters) |
| [charactercheck](https://github.com/chaoz23/charactercheck) | verdict | Character-sheet derivation with per-stat provenance |
| [dmcheck](https://github.com/chaoz23/dmcheck) | verdict | Table-conduct findings against a table charter |
| [table-kit](https://github.com/chaoz23/table-kit) | transport | Hybrid-table transport + session ledger (one JSONL per session) |
| [inkcheck](https://github.com/chaoz23/inkcheck) | adjacent | ink story structure (CI verdicts) |
| [loudcheck](https://github.com/chaoz23/loudcheck) | adjacent | Broadcast loudness vs formal standards |

- **verdict** — adjudicates D&D content or conduct and returns a ruling. Bound by
  every clause.
- **transport** — moves and records what happens at a table. Emits a verdict only
  about its own coverage and QC. Clauses 1 and 3 bind it *where it emits a
  verdict*, and not elsewhere.
- **adjacent** — a check-family tool in a different domain. Bound by clauses 2–6
  and by the agent-first spirit of clause 7, but not by the D&D choreography
  below, and not by the honest-lane contract (clause 1) — their refusals are
  expressed in output, and exit 2 means a usage/environment error.

## The contract

1. **Exit codes are the verdict.** `0` = pass/legal/clean · `1` = fail/illegal/
   findings, in every member. The **honest lane** — a first-class
   cannot-adjudicate answer meaning the question is outside the tool's codified
   jurisdiction, or that the tool cannot answer it from the evidence it has
   (unknown content, discretion, ambiguity, incomplete coverage) — is the
   contract of the verdict class: srdcheck and dmcheck use exit `2`;
   charactercheck uses exit `2` for unhandled content and `3` for could-not-
   retrieve. Consuming agents route the honest lane to a human; never retry or
   guess. Usage errors are **not** the honest lane and should not share its exit
   code; srdcheck's exit `3` is the family precedent. Each SKILL.md states its
   own tool's exact contract — read that, not this table, when invoking, and see
   clause 7 on how that statement is kept true.
2. **Deterministic verdict paths.** No model invocation, no network, no
   randomness anywhere in a verdict path. A model call to compute what a lookup
   or formula can decide is a defect. Same input, same verdict, every time.
3. **Verdicts carry evidence.** Each tool cites its standard in its own idiom:
   srdcheck quotes SRD text with section/page; charactercheck emits per-stat
   provenance; dmcheck cites charter clauses; loudcheck cites the published
   standard and exact deltas. A bare boolean is not a verdict.
4. **Advisory by default; humans own the table.** No tool marks its own output
   binding. Ambiguity never produces an accusation (dmcheck's
   no-false-accusation contract is the strongest form; the family default is the
   same stance).
5. **Standards are pinned.** Rule/standard content is versioned separately from
   tool code where it exists as content (srdcheck adapters carry `version` +
   sha256 digest, printed by `capabilities` and stamped on every verdict as
   `adapter@version`). A tool upgrade must not silently flip a verdict; flips
   require a content-version bump.
6. **Licensing is a gate.** SRD content under its published license only
   (5.1: CC-BY-4.0; 5.2.1 per its terms), attribution intact. No reproduced
   non-covered text anywhere — fixtures and test corpora included.
7. **Agent-first surfaces.** What each class must ship:

   | Surface | verdict | transport | adjacent |
   | :-- | :-: | :-: | :-: |
   | `SKILL.md` front door | ✅ | ✅ | ✅ |
   | `tool.json` at repo root | ✅ | ✅ | ✅ |
   | `llms.txt` | ✅ | ✅ | ✅ |
   | CLI `--schema` **flag** | ✅ | ✅ | ✅ |
   | CLI `--pipe` | ✅ | — | — |
   | MCP server | ✅ | — | — |

   **A member declares its own class** in `tool.json` as
   `"family_class": "verdict" | "transport" | "adjacent"`. The declaration lives
   in the artifact, not in this file's prose, so tooling reads it without
   parsing markdown and a member owns its own classification. A member that
   declares no class is not assumed to have one: the conformance gate reports
   the omission and states which class-gated surfaces it therefore did not
   check, rather than guessing.

   `--pipe` is one-query-in / one-verdict-out. It binds the verdict class because
   that shape is what a verdict tool *is*; a transport that records a session has
   no such shape, and requiring it there would produce a surface with no honest
   semantics. The same reasoning applies to an MCP server: a verdict tool is worth
   exposing as callable tools, a session ledger is driven by the table it records.

   The **acceptance test** for `SKILL.md` is: a fresh-context agent, given only
   that file, can produce a well-formed invocation. That test checks
   *invocability*. It does not check *truth*, and every member's SKILL.md passed
   it while misstating its own exit contract. So `SKILL.md` carries a second
   obligation: **its claims must be executable and executed.**
   `scripts/family_conformance.py` in this repo runs a member's CLI and diffs
   observed exit codes and output streams against what its SKILL.md says.

   **Open gaps, named rather than implied:** dmcheck ships no `--pipe`
   ([dmcheck#14](https://github.com/chaoz23/dmcheck/issues/14)); table-kit
   exposes `--schema` only as a subcommand
   ([table-kit#23](https://github.com/chaoz23/table-kit/issues/23)).

## Cross-tool choreography

Applies to the verdict and transport classes.

- **Live ruling:** srdcheck (rule) → exit 2 → DM rules → table-kit ledger
  entry, tagged ruling-not-rule.
- **Character audit:** charactercheck derive → underivable names → srdcheck
  jurisdiction → DM for the remainder.
- **Session retro:** dmcheck over charter + table-kit session JSONL →
  findings or silence → humans decide any process change.

## Versioning of this contract

This file is versioned by its heading. Changes that tighten or add clauses
require a version bump and a changelog entry in the PR that makes them; sibling
repos pin by link, not by copy.

### Changelog

- **v2.1** — Members declare their class machine-readably as `family_class` in
  `tool.json`. v2 introduced classes but left them stated only in this file's
  members table, so the conformance gate had no way to apply clause 7 per class
  and reported `--pipe` as missing on a transport member that v2 exempts. An
  undeclared class is reported as such, never guessed.
- **v2** — Introduced member classes (verdict / transport / adjacent) and stated
  clause 7 per class, so `--pipe` and an MCP server bind the tools whose shape
  they fit. Corrected the preamble's claim to be wholly descriptive. Widened
  clause 1's honest lane to include *cannot answer from the evidence available*,
  which is what the reference implementation already does, and stated explicitly
  that usage errors must not share the honest lane's exit code. Added the
  SKILL.md truth obligation and the conformance gate. Named the two open clause-7
  gaps inline. Recorded inkcheck and loudcheck as an adjacent class rather than
  as members carrying a grudging exception.
- **v1** — Initial descriptive contract.
