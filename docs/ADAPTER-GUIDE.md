# Writing an srdcheck adapter

The kernel knows no game. All rule content loads from adapter packages; the
catalog points, never hosts. Three live examples span the tiers:

| tier | example | what it ships |
|---|---|---|
| registry-only | `srd-5.1` | entities + provenance manifest + sources; answers `jurisdiction` and `cite` |
| full | `srd-5.2.1` | + atoms, queries with schemas, handlers, spell facts |
| tutorial | `toy-tictactoe` | the smallest full adapter; read it first |

## Non-negotiables (enforced by `srdcheck conformance <id>`)
1. **Provenance manifest** — name, license, attribution text, hash-pinned
   source document. No third-party conversions of licensed content.
2. **Schema-declared inputs** with `additionalProperties: false`; unknown
   keys must refuse (exit 2), never pass silently.
3. **Honest refusal**: exit 2 is "not mine to answer," a first-class outcome.
4. **Census anchoring** for every extracted registry: registry size checked
   against an independent count of the source's own headings, in CI.
5. **Rebuild reproducibility**: one committed script reproduces every
   committed artifact byte-for-byte, in CI.
6. **Golden verdicts**: pin behavior before refactors (scripts/build_golden.py).

## Start
```
srdcheck new-adapter my-ruleset
srdcheck conformance my-ruleset   # after pointing SRDCHECK_ADAPTERS at it
```
Then follow toy-tictactoe for handlers and srd-5.2.1 for extraction patterns
(build_entities.py, build_spell_facts.py, the census oracles in tests/).

## What the kit will not accept
Blended scores, uncited verdicts, silent parameter swallowing, or content
whose license you cannot carry. The honesty machinery is the entry ticket —
it is why a verdict from any adapter is worth trusting at a table.
