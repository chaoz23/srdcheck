# Contributing

Contributions are welcome — from humans and from agents. The bar is the same
for both: the [product truths](docs/product-truths.md) are the review criteria,
and CI enforces most of them mechanically.

## The one rule that is never waived: provenance

**All rule content must derive from the official SRD 5.2.1 document** (fetched
and hash-verified by `sources/fetch.sh`). Every rule atom carries a citation
with a verbatim quote; CI rebuilds the entity registry from the source document
and fails on drift.

Do **not** submit content from the Player's Handbook, D&D Beyond, Sage Advice,
third-party books, or homebrew — even paraphrased. PRs adding non-SRD content
will be closed regardless of quality; it's a license boundary, not a quality
judgment. If you want another ruleset supported, write an **adapter** for
content you have rights to (see [docs/adapter-spec.md](docs/adapter-spec.md))
and host it in your own repo — the catalog points, it never hosts.

## What makes a good PR here

- A new rule atom cites section, page, and verbatim quote from the SRD text.
- A new handler's every verdict path cites; honest exit 2 at the edges beats
  guessed coverage (a wrong verdict is the only unforgivable bug).
- Kernel changes contain zero game vocabulary (a lint test will catch you).
- New adjudication comes with goldens; new enumeration comes with
  enumerate/validate consistency coverage.

## Dev setup

```console
$ pip install -e ".[dev]"
$ bash sources/fetch.sh && python sources/extract.py   # SRD text for citation work
$ python -m pytest tests/ -q
```
