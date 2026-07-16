# Adapter spec — v0 (UNSTABLE)

> This spec is not stable. It will change until a second adapter — even a toy one —
> has been built against it to prove it isn't secretly SRD-shaped. Do not build
> against it yet; watch the repo for the v1 declaration.

An adapter is a directory that teaches the content-neutral kernel one ruleset:

```
adapters/<name>/
  manifest.json    # provenance — REQUIRED
  entities.json    # what content exists — REQUIRED
  atoms/*.json     # rule atoms: parameters + citations
  handlers.py      # query handlers (the game logic)
```

## manifest.json

Name, version, ruleset, **source document + sha256**, license, required attribution,
maintainer. Every verdict cites through this manifest — an adapter without clean
provenance is not an adapter.

## entities.json

`{category: [names…]}`. This powers the jurisdiction gate: any entity not present
in a loaded adapter yields an honest exit 2, never a guess. Generate it from the
source document (see `adapters/srd-5.2.1/build_entities.py`), don't hand-type it.

## Rule atoms

Small JSON objects: `id`, `kind` (`grant` | `prohibition` | `limit` | `definition`),
`params`, and a `citation` (`section`, `page`, `quote` — the quote is the actual
source text). Atoms carry the *facts*; they do not carry logic.

## handlers.py

Exports `HANDLERS: {query_type: fn(adapter, params) -> Verdict}`. Handlers are the
code escape hatch: control flow lives here, but every fact a handler uses must come
from an atom, and every verdict path must cite. The kernel never imports game
vocabulary — a lint test enforces it.

## The deal

The kernel promises adapters: deterministic dispatch, the verdict envelope,
the jurisdiction gate, and zero opinions about your game. Adapters promise the
kernel: provenance, citations on every path, and honest exit 2 at their edges.
