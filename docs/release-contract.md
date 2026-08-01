# Release contract

This document carries the v0.5 release truth repaired in issues #16, #17, #18,
#19, and #21 forward into the v0.6 machine compatibility contract.

## Version identities

- **Engine/package version** comes only from `project.version` in
  `pyproject.toml`. Source-checkout detection, installed package metadata, MCP
  `serverInfo`, capabilities, generated metadata, and registry metadata must
  match it.
- **Adapter versions** remain independent and come from each `manifest.json`.
  Bundled adapters also declare additive `data_version` and `rules_version`
  identities. Older/external manifests remain conformant: their aggregate
  adapter version is the fallback for a split identity only when that key is
  absent. Every present adapter, data, or rules identity must be a complete
  SemVer 2.0 string; an explicit empty or malformed identity fails conformance
  rather than being masked by the aggregate version. A correction changes the
  affected adapter identity; it does not pretend to be an engine release.
- **Capability schema version** versions the shape of `srdcheck capabilities`.
- **Refusal contract version** versions the machine vocabulary and canonical
  recovery mappings emitted for exit-code-2 results.
- **MCP protocol versions** declare the revisions this server implements and
  the preferred revision it offers when a client requests an unsupported one.

`python -m srdcheck capabilities` is the machine-readable source for all five
and records the exact engine/adapter/data/rules/digest release tuple.
Adapter digests bind the provenance, entities, query schemas, atoms, and shipped
per-page citation text used by a process.

Version changes follow these rules:

- Engine patch/minor/major versions cover compatible fixes, additive public
  engine behavior, and breaking engine/API behavior respectively. During
  alpha, machine semantics are supported for the current and immediately
  previous engine minor (`N/N-1`).
- Adapter versions cover executable handlers and rules data. Corrected
  extraction or a demonstrably wrong ruling is a documented patch; additive
  optional query/schema surface is a minor; renamed or removed tools, newly
  required inputs, and other incompatible schema changes are major.
- Verdict and capabilities schema identities change whenever consumers must
  interpret their shape differently. Existing field meanings and types are
  stable within an identity. Because verdict v1 rejects unknown top-level
  fields, its property set is frozen; adding an emitted top-level field requires
  a new schema identity and migration. Capabilities schema 2.0 is introduced in
  engine 0.6.0 for the machine contracts, exact release tuple, refusal
  recovery contract, query coverage, and target map. MCP protocol support is
  reported separately and never inferred from the engine or adapter version.
- The templated `why` string is explanatory, non-contractual prose. Exact
  goldens still make wording changes visible in review, but semantic
  compatibility fixtures intentionally project it out.
- First-party exit-code-2 results put `reason_code`, `recoverability`,
  `missing_inputs`, and `suggested_next_action` inside the existing verdict
  `data` object; authority-bound results also carry `required_authority`. The
  vocabulary and mappings are published by capabilities and documented in
  [refusal recovery](refusal-recovery.md). Clients never parse `why` for this
  control flow.
- Every shipped change that corrects a wrong ruling identifies the affected
  adapter, queries, rule IDs, exact corrected engine/adapter/data/rules tuple,
  and migration note in `docs/ruling-corrections.json`. High/critical
  corrections also require a public notice and caller action; CI validates the
  record.

The generated `docs/capability-map.json` and `.md` distinguish shipped tools,
their checked/unchecked scope, and target architecture. CI checks both files
against runtime capability and adapter metadata.

## Installed citation data

Official SRD PDFs are provenance/build inputs, not runtime dependencies. The
per-page CC-BY-4.0 text extractions that `srdcheck cite` reads are committed,
freshness-checked against the hash-pinned PDF extraction, and included in wheel
and sdist package data with the required NOTICE and adapter attribution. Source
PDFs are excluded from release artifacts.

## Validation

Every request is validated against its adapter-declared JSON Schema before a
handler runs. Schema failures are verdict-level honest refusals with structured
`validation_errors` plus machine recovery metadata; malformed JSON-RPC
envelopes remain protocol errors.
Every MCP tool publishes the common verdict output schema, and results are
validated before they leave the process.

The stdio MCP server implements the required initialize/initialized lifecycle,
prefers the `2025-06-18` protocol revision, and also negotiates its declared
`2025-03-26` compatibility revision. It advertises only static tools. Calls are
synchronous and bounded, so it emits no progress or logging notifications; it
accepts cancellation notifications without advertising asynchronous work.
Clients must close stdin to shut it down, as required by the stdio lifecycle.

## Artifact gate

CI builds wheel and sdist from a clean tree, installs each outside the checkout,
pins archive metadata to the source commit timestamp for reproducibility, and
verifies CLI, cite, library, capabilities, and MCP behavior. Tagged builds
also produce checksums, an SPDX SBOM, GitHub build provenance, and downloadable
artifacts. Artifact installation uses no package index and no isolated build
environment after the build backend has been provisioned, so both wheel and
sdist journeys prove the runtime package is self-contained.

Publishing to PyPI remains a separate, explicitly authorized action. After a
package is published, publishing its GitHub release triggers `registry-smoke`;
the same check can be dispatched manually with an exact version. It downloads
both registry artifacts, disconnects pip from the registry, and repeats the
headline journeys on Python 3.10 and 3.13. Publish the package before the GitHub
release so a missing or delayed registry artifact fails visibly.
