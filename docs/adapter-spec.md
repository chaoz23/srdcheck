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

## The deal

The kernel promises adapters: deterministic dispatch, the verdict envelope,
the jurisdiction gate, and zero opinions about your game. Adapters promise the
kernel: provenance, citations on every path, and honest exit 2 at their edges.
