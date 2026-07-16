# srdcheck

**Deterministic rails for game-running agents — so intelligence is spent only where intelligence is the only thing that works.**

Machine verdicts over the rules of the System Reference Document 5.2.1: cited, reproducible, delivered in milliseconds with zero tokens, and honest enough to refuse questions that aren't the rules' to answer. The rules lawyer for agents.

> **Status: pre-release, building in the open.** The kill tests that shaped the product — including the one that killed half our original idea — are in [eval/RESULTS-phase0.md](eval/RESULTS-phase0.md), and the with/without-rails demo is in [demo/mage-hand/](demo/mage-hand/). No tagged release yet; the truth scorecard below ships with v0.1.

## Why this exists

A model running a game is a brilliant improviser with a finite attention budget. Every mechanical micro-check it handles in-context — *is this legal, is that slot spent, does the reaction refresh this round* — spends tokens and attention that belong to the only work that needs a mind: the story, the improvisation, the table. And the checks a model *can* answer, it cannot **prove**, cannot **reproduce**, and — as our own benchmark showed — will not **refuse** when the question is outside the rules' jurisdiction.

We tested this before building. Frontier models answered our SRD rules questions nearly perfectly — and confidently ruled on house rules, GM discretion, and content that doesn't exist in the SRD, where the only correct answer is "not my call." Small local models got 19–30% wrong with zero refusals. So srdcheck does not compete with what models know. It is a rail: state in, verdict out, citations attached, deterministically, every time.

## What it is

srdcheck answers one kind of question: *is this legal under the rules?* — and one better one: *what is legal right now?*

- **Verdicts, not vibes.** Exit code `0` = legal, `1` = illegal, `2` = cannot adjudicate. Every verdict carries its chain of SRD 5.2.1 citations. A rule we cannot cite is a rule we do not have.
- **Judge, never simulate.** No dice, no narration, no owned game state. State comes in with the query; a verdict goes out. The kernel is a stateless pure function — embeddable in anyone's DM product, VTT, or agent.
- **Deterministic and fast.** No LLM call anywhere in the verdict path. Runs local and offline.
- **For agents first.** MCP + CLI, `--pipe`, `--schema`, `tool.json` at the repo root. Humans get a plain-English *why* in the same payload.

- **Rulesets are adapters.** The kernel knows no game; all rule content loads from adapter packages, each carrying its own provenance manifest — source document, hash, license, attribution — that every verdict cites through. The SRD 5.2.1 adapter ships in this repo as the reference implementation. Anyone can build an adapter for another ruleset — a community, a private table, or a publisher shipping a first-party adapter for their own IP — and their content never passes through this project. The adapter catalog points; it never hosts.

See [docs/product-truths.md](docs/product-truths.md) for the invariants this project holds itself to, and [docs/anatomy-of-a-turn.md](docs/anatomy-of-a-turn.md) for where srdcheck sits in a game-running agent's pipeline — a combat turn, a stealth infiltration, and the Mage Hand test, worked end to end.

## Try it now

The jurisdiction kernel and the first adapter slice are runnable today:

```console
$ python -m srdcheck jurisdiction "Fireball"          # exit 0 — known content
$ python -m srdcheck jurisdiction "Hexblade"          # exit 2 — not in the SRD, honestly refused
$ python -m srdcheck query mage-hand.use '{"kind": "attack"}'
{
  "verdict": "illegal",
  "exit_code": 1,
  "why": "The hand can't attack.",
  "citations": [{"section": "SRD 5.2.1 p.145 'Spells > Mage Hand'", "page": 145,
                 "quote": "The hand can't attack"}],
  "rule_ids": ["mage-hand.cant-attack"],
  "adapter": "srd-5.2.1@0.1.0-unstable"
}
$ python -m srdcheck --schema                          # I/O contract for agents
```

Deterministic, offline, no tokens, sub-millisecond. The query surface is small and unstable until v0.1 — the architecture (kernel + [adapters](docs/adapter-spec.md)) is the point.

## For agents (MCP)

srdcheck is an MCP server with zero dependencies — stdlib only, nothing to install beyond cloning:

```json
{
  "mcpServers": {
    "srdcheck": {
      "command": "python3",
      "args": ["-m", "srdcheck.mcp"],
      "cwd": "/path/to/srdcheck"
    }
  }
}
```

Seven tools: `jurisdiction`, `turn_plan`, `turn_options`, `reaction_available`, `roll_compose`, `attack_modifiers`, `mage_hand_use`. Every call returns the same verdict object as the CLI (verdict, exit_code, why, citations with source quotes) as structured content. An `illegal` verdict is a result, not an error; `cannot-adjudicate` is an honest refusal, not a failure. Tool descriptions and schemas come from the loaded adapters, so new adapters extend the tool list without kernel changes. See also [`tool.json`](tool.json) for the CLI surface.

## The benchmark

[`bench/`](bench/) is the rules-fidelity referee: versioned question sets with SRD-cited gold verdicts, a harness that scores any model or agent (`gemini:`, `ollama:`, or `cmd:your-agent` on stdin/stdout), and a [generated scorecard](bench/scorecard.md) that reports wrong-rate, refusal-rate, and false-confidence separately, per category, with no aggregate number — ever. Its first published finding: frontier models ace codified rules and fail by *false confidence* exactly where the rules end. Benchmark your own DM product with one command.

## Truth scorecard

Every tagged release publishes a scorecard against the product truths — generated by CI, never hand-edited, no aggregate score.

*(No releases yet. First scorecard ships with v0.1.)*

## Licensing

- Code: MIT.
- `data/`: includes material derived from the System Reference Document 5.2.1 under CC-BY-4.0 — see `sources/README.md` for provenance and the required attribution.
- srdcheck is unofficial and is not affiliated with or endorsed by Wizards of the Coast.

## Prior art

srdcheck stands on lessons from Temple of Elemental Evil / Temple+ (dispatcher architecture), PCGen (prerequisite predicates), the FoundryVTT PF2e system (rules as data), Datasworn (official rules-as-JSON precedent), and FIREBALL (structured play state). Patterns were studied; no code was taken from any of them.
