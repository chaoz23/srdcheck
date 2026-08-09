# The check family — shared contract (v1, descriptive)

Canonical copy: this file, in [srdcheck](https://github.com/chaoz23/srdcheck)
(the family's reference implementation). Sibling repos link here. This
document describes the contract the family already implements; it becomes
prescriptive only for new tools.

## Members

| Tool | Verdict domain |
| :-- | :-- |
| [srdcheck](https://github.com/chaoz23/srdcheck) | Written-rules legality (SRD 5.2.1 + 5.1 adapters) |
| [charactercheck](https://github.com/chaoz23/charactercheck) | Character-sheet derivation with per-stat provenance |
| [dmcheck](https://github.com/chaoz23/dmcheck) | Table-conduct findings against a table charter |
| [table-kit](https://github.com/chaoz23/table-kit) | Hybrid-table transport + session ledger (one JSONL per session) |
| [inkcheck](https://github.com/chaoz23/inkcheck) | ink story structure (CI verdicts) |
| [loudcheck](https://github.com/chaoz23/loudcheck) | Broadcast loudness vs formal standards |

## The contract

1. **Exit codes are the verdict.** `0` = pass/legal/clean · `1` = fail/illegal/
   findings · `2` = **cannot-adjudicate — the honest lane.** Exit 2 is a
   first-class answer meaning the question is outside the tool's codified
   jurisdiction (unknown content, discretion, ambiguity). It is never an
   error, and consuming agents must route it to a human rather than retry or
   guess. Higher codes (3+) are usage/internal errors, never verdicts.
2. **Deterministic verdict paths.** No model invocation, no network, no
   randomness anywhere in a verdict path. A model call to compute what a
   lookup or formula can decide is a defect. Same input, same verdict, every
   time.
3. **Verdicts carry evidence.** Each tool cites its standard in its own
   idiom: srdcheck quotes SRD text with section/page; charactercheck emits
   per-stat provenance; dmcheck cites charter clauses; loudcheck cites the
   published standard and exact deltas. A bare boolean is not a verdict.
4. **Advisory by default; humans own the table.** No tool marks its own
   output binding. Ambiguity never produces an accusation (dmcheck's
   no-false-accusation contract is the strongest form; the family default is
   the same stance).
5. **Standards are pinned.** Rule/standard content is versioned separately
   from tool code where it exists as content (srdcheck adapters carry
   `version` + sha256 digest, printed by `capabilities` and stamped on every
   verdict as `adapter@version`). A tool upgrade must not silently flip a
   verdict; flips require a content-version bump.
6. **Licensing is a gate.** SRD content under its published license only
   (5.1: CC-BY-4.0; 5.2.1 per its terms), attribution intact. No reproduced
   non-covered text anywhere — fixtures and test corpora included.
7. **Agent-first surfaces.** Every tool ships: CLI with `--pipe` and
   `--schema`, `tool.json` at repo root, `llms.txt`, an MCP server, and a
   `SKILL.md` front door whose acceptance test is: a fresh-context agent,
   given only the SKILL.md, can produce a well-formed invocation.

## Cross-tool choreography

- **Live ruling:** srdcheck (rule) → exit 2 → DM rules → table-kit ledger
  entry, tagged ruling-not-rule.
- **Character audit:** charactercheck derive → underivable names → srdcheck
  jurisdiction → DM for the remainder.
- **Session retro:** dmcheck over charter + table-kit session JSONL →
  findings or silence → humans decide any process change.

## Versioning of this contract

This file is versioned by its heading (v1). Changes that tighten or add
clauses require a version bump and a changelog entry in the PR that makes
them; sibling repos pin by link, not by copy.
