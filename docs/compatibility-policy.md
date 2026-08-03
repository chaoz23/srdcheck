# Machine compatibility and ruling corrections

This is the public compatibility contract for engine `0.x`. The machine-readable
identities are emitted by `srdcheck capabilities`; this page explains how to use
them.

## What is stable

- The verdict schema and capabilities schema have identities independent of the
  package version. `srdcheck --schema`, every MCP `outputSchema`, and
  `srdcheck capabilities` publish them.
- Within one schema version, existing fields keep their type and meaning, and
  existing required inputs do not become stricter. The verdict v2 envelope has
  `additionalProperties: false`, so its top-level property set is frozen: a new
  emitted top-level field requires a new verdict schema identity and migration.
  Query-specific objects inside `data` may add fields only when that query's
  documented field contract permits them; consumers must not treat this as a
  license for silent semantic reinterpretation.
- Each engine minor supports the current and immediately previous engine-minor
  semantics (`N/N-1`). The executable fixture in
  `tests/compat/semantic-v0.7.json` is the current previous-minor floor. Its
  adapter version is historical provenance, not a pin on the current adapter:
  cases run against the current adapter with the same versioned ruleset
  identifier, so an independent data-only adapter patch does not invalidate the
  engine window by itself.
- Stable semantics are the verdict/exit-code pairing, rule identifiers,
  citation identity (ordered section/page projection), and structured data used
  by a fixture. Citation quote bytes belong to the independently versioned
  adapter data and are bound by its digest rather than the engine-minor window.
  JSON object order is never contractual.
- `why` is deliberately **non-contractual explanatory prose**. It remains
  templated and review-tested, but may become clearer without a schema or
  compatibility change. Agents must not parse it to choose control flow.

A new schema version requires migration notes. Removing or reinterpreting a
machine field, query, reason code, or enum is not an additive change. Engine
0.6.0 moved `capabilities` from schema 1.0 to 2.0 because it added machine
contracts, exact release tuples, refusal recovery, checked/unchecked query
coverage, and targets. Engine 0.8.0 moves verdicts from schema 1.0 to 2.0. The
v2 migration keeps every v1 field and adds four required fields:
`coverage_level`, `checked_scope`, `unchecked_scope`, and `assumptions`.
Consumers that validate the closed v1 schema must negotiate v2 through
`--schema`, MCP `outputSchema`, or capabilities before accepting the new
envelope; they must not silently discard the scope boundary.

Exit-code-2 recovery metadata is additive inside the verdict's existing open
`data` object, so it does not change the verdict v2 top-level shape. Its
reason codes, recoverability values, next actions, canonical mappings, and
authority semantics form a separately identified machine contract published by
`srdcheck capabilities`. See [refusal recovery](refusal-recovery.md). Removing
or reinterpreting one of those values requires a contract migration; adding
explanatory detail to `why` does not.

## Exact release tuple

The engine and an adapter do not share a version clock. Every runtime capability
record contains this tuple:

1. engine/package version;
2. adapter version and digest;
3. rules-data version; and
4. executable-rules version.

The explicit data/rules identities are additive manifest fields. An older or
third-party adapter that has only `version` remains conformant; its aggregate
version is used for both identities. Every present identity is strict SemVer
2.0; fallback is based on key absence, so an explicit empty or malformed split
identity fails conformance instead of being silently masked. The digest still
binds the exact manifest, registries, query schemas, atoms, handlers, and
packaged citation text.

## Wrong rulings are corrected, not preserved

Compatibility never freezes a demonstrably wrong rules result. Correct it in
the earliest safe patch, bump the affected adapter's executable-rules and/or
data identity, and update the previous-minor fixture deliberately. Record the
change in `docs/ruling-corrections.json`.

Every correction names the adapter identifier, affected queries and rule IDs,
the exact engine/adapter/data/rules versions first carrying it, and a migration
note. A `high` or `critical` correction must also include a concise public
notice and caller action. CI rejects an incomplete record. This exception is
intentionally narrower than ordinary semantic change: a preferred wording, new
feature, or disputed table ruling is not a correctness correction.

srdcheck distinguishes an SRD-derived result from an exercise of table
authority. The authorized DM may be a human or the calling agent itself; when
the rules leave a ruling to that authority, the agent-DM may rule directly and
record the decision as a ruling rather than pretending it was derived from the
SRD.
