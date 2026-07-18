# Adapter spec — v0.9 (release candidate)

> **Status:** the spec has now survived its first non-SRD adapter —
> [`srdcheck/adapters/toy-tictactoe/`](../srdcheck/adapters/toy-tictactoe/), a game with boards
> instead of turns, cited to a Markdown file instead of a PDF — with zero kernel
> changes and one spec amendment (repo-local sources, below). It is a release
> candidate: one external adopter away from v1. Build against it with the
> expectation of at most minor changes.

An adapter is a directory that teaches the content-neutral kernel one ruleset:

```
srdcheck/adapters/<name>/
  manifest.json    # provenance — REQUIRED
  entities.json    # what content exists — REQUIRED
  atoms/*.json     # rule atoms: parameters + citations
  queries.json     # query-type descriptions + input schemas (agent discovery)
  handlers.py      # query handlers (the game logic)
```

## manifest.json

Name, version, ruleset, **source document + sha256**, license, required attribution,
maintainer. Every verdict cites through this manifest — an adapter without clean
provenance is not an adapter. The source may be a fetched document (`url` +
`sha256`) or a repo-local file (`path` + `sha256`) for self-authored or bundled
rules texts.

## entities.json

`{category: [names…]}`. This powers the jurisdiction gate: any entity not present
in a loaded adapter yields an honest exit 2, never a guess. Generate it from the
source document (see `srdcheck/adapters/srd-5.2.1/build_entities.py`), don't hand-type it.

## Rule atoms

Small JSON objects: `id`, `kind` (`grant` | `prohibition` | `limit` | `definition`),
`params`, and a `citation` (`section`, `page`, `quote` — the quote is the actual
source text). Atoms carry the *facts*; they do not carry logic.

## queries.json

`{query_type: {description, inputSchema}}`. This is how agents discover what an
adapter can adjudicate: the MCP server and `--schema` build their tool surfaces
from it. Discoverability metadata travels with content, like rules — new adapters
extend the tool list with zero kernel changes.

## handlers.py

Exports `HANDLERS: {query_type: fn(adapter, params) -> Verdict}`. Handlers are the
code escape hatch: control flow lives here, but every fact a handler uses must come
from an atom, and every verdict path must cite. The kernel never imports game
vocabulary — a lint test enforces it.

## Versioned identifiers & the stable consumer interface

An adapter directory is named by a **versioned identifier** (e.g. `srd-5.2.1`).
A different version of the same ruleset ships as a *separate* identifier
(`srd-5.1`, `srd-5.3`), so versions coexist and a new one is added without a
breaking change — the version is first-class, not baked into the code.

Downstream tools consume an adapter through the supported top-level API, never
by reaching into internal file paths:

```python
from srdcheck import load_adapter, available_adapters
a = load_adapter("srd-5.2.1")
a.categories(); a.names(category); a.record(category, name); a.query(qt, params)
```

Entity entries are either bare name strings or objects with a `name` field plus
adapter-defined facts (e.g. a creature's `cr`/`xp`/`citation`); the handle
exposes both without the kernel interpreting the facts.

## The version-migration contract

Supporting a new version of a ruleset (e.g. SRD 5.1 alongside 5.2.1) is cheap and
isolated, because **the version-coupling lives entirely in the build layer, never
in the kernel or consumers.** Building the 5.1 adapter established the contract:

- **Each version is a self-contained adapter.** It owns its `sources/`
  (hash-pinned document + fetch script), its **version-specific**
  `build_entities.py`, and its committed `entities.json`. Nothing at the repo
  root is version-specific.
- **A new version = one version-specific build script.** Different editions
  format differently (5.1 writes `Challenge 10 (5,900 XP)`, 5.2.1 writes
  `CR 10 (XP 5,900; PB +4)`; the 5.1 PDF extracts with whitespace/hyphen noise).
  So the build script is per-version. But it emits the *same standard files*, so
  **the kernel, the query handlers, the public API, and every consumer are
  untouched** — a new version drops in via `load_adapter("srd-5.3")`.
- **Completeness oracle, always.** Each version's registry ships with a CI check
  that its size equals an independent anchor count in that version's text
  (`Casting Time:` blocks, stat-block markers). Silent incompleteness fails the
  build — a hard-won rule.
- **`"default_load": false`** keeps an older/reference version loadable-on-demand
  without blurring the primary ruleset: it answers `load_adapter(...)` and
  `edition_check(...)` but stays out of the default engine (so `jurisdiction`
  and the query surface remain the current edition).
- **Cross-version comparison is caller-parameterized**, not baked in:
  `edition_check(name, category, current, priors)` does a content-neutral
  set-difference across versions — adapters never reference each other.

The kernel never knows the game *or the version*; multi-version support is proven
by 5.1 loading with zero kernel changes.

## The deal

The kernel promises adapters: deterministic dispatch, the verdict envelope,
the jurisdiction gate, and zero opinions about your game. Adapters promise the
kernel: provenance, citations on every path, and honest exit 2 at their edges.
