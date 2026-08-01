# Release contract

This document specifies the v0.5 release truth repaired in issues #16, #17,
#18, #19, and #21.

## Version identities

- **Engine/package version** comes only from `project.version` in
  `pyproject.toml`. Source-checkout detection, installed package metadata, MCP
  `serverInfo`, capabilities, generated metadata, and registry metadata must
  match it.
- **Adapter versions** remain independent and come from each `manifest.json`.
  A rules-data correction changes the adapter version; it does not pretend to
  be an engine release.
- **Capability schema version** versions the shape of `srdcheck capabilities`.
- **MCP protocol versions** declare the revisions this server implements and
  the preferred revision it offers when a client requests an unsupported one.

`python -m srdcheck capabilities` is the machine-readable source for all four.
Adapter digests bind the provenance, entities, query schemas, atoms, and shipped
per-page citation text used by a process.

Version changes follow these rules:

- Engine patch/minor/major versions cover compatible fixes, additive public
  engine behavior, and breaking engine/API behavior respectively.
- Adapter versions cover executable handlers and rules data. Corrected
  extraction or a demonstrably wrong ruling is a documented patch; additive
  optional query/schema surface is a minor; renamed or removed tools, newly
  required inputs, and other incompatible schema changes are major.
- The capabilities `schema_version` changes whenever consumers must interpret
  its shape differently. MCP protocol support is reported separately and never
  inferred from the engine or adapter version.
- Every shipped change that intentionally alters a golden verdict identifies
  the affected adapter version and correction in release notes.

## Installed citation data

Official SRD PDFs are provenance/build inputs, not runtime dependencies. The
per-page CC-BY-4.0 text extractions that `srdcheck cite` reads are committed,
freshness-checked against the hash-pinned PDF extraction, and included in wheel
and sdist package data with the required NOTICE and adapter attribution. Source
PDFs are excluded from release artifacts.

## Validation

Every request is validated against its adapter-declared JSON Schema before a
handler runs. Schema failures are verdict-level honest refusals with structured
`validation_errors`; malformed JSON-RPC envelopes remain protocol errors.
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
