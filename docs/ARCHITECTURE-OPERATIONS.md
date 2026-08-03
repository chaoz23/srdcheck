# Architecture handoff

SRDCheck is a zero-runtime-dependency Python package with three public entry
paths—library, CLI, and stdio MCP—over one deterministic engine. It owns no
network service, database, user identity, dice, narration, or authoritative
table state.

## Runtime map

1. `srdcheck.access` discovers bundled adapters and publishes capabilities.
2. `srdcheck.engine.Engine` validates provenance metadata and dispatches a
   named query to a loaded adapter.
3. `srdcheck.adapter.Adapter` loads manifest, registry, atoms, query schemas,
   citation text, and trusted executable handlers.
4. Adapter handlers return native verdicts; the kernel attaches scope, fact,
   table-decision, and mutation provenance.
5. `srdcheck.cli` and `srdcheck.mcp` validate and serialize the same verdict
   contract. `srdcheck.observability` emits optional metadata out of band.

The trust boundaries are consequential:

- bundled/executable adapters are trusted Python code, not sandboxed data;
- source text is licensed input and must remain hash/citation verified;
- table decisions and state writes remain caller/host responsibilities;
- telemetry is metadata-only, disabled by default, and host-retained; and
- PyPI and MCP Registry publication are release operations, not runtime needs.

## Change ownership

| area | required review concern |
|---|---|
| kernel and schemas | determinism, content neutrality, N/N-1 compatibility |
| adapter handlers and atoms | rules accuracy, exact SRD citation, correction record |
| benchmark questions/golds | independent experienced-DM review; engine-derived fixtures labeled separately |
| packaging and workflows | clean artifacts, minimum runtime, provenance, least privilege |
| observability | payload exclusion, non-interference, retention ownership |
| documentation | shipped/target distinction, licensing, support truthfulness |

`CODEOWNERS` currently routes every area to one bootstrap owner. That makes the
single-maintainer risk visible; it does not constitute independent review.

## Operator checks

```bash
python -m pytest tests/ -q
python scripts/check_repo_hygiene.py
python scripts/build_golden.py --check
python scripts/truth_scorecard.py --check
python scripts/capability_map.py --check
python -m srdcheck capabilities
```

For releases use only `docs/RELEASE.md`. For a ruling defect, privacy event, or
supply-chain failure use `docs/INCIDENT-RESPONSE.md`. Supported environments
and response boundaries are in `docs/SUPPORT.md` and `docs/support-matrix.md`.

## High-risk failure modes

- a partial checked scope is presented as global legality;
- a rule path lacks its exact source citation or uses non-SRD content;
- adapter executable code is treated as untrusted/declarative content;
- generated metadata drifts from runtime contracts;
- a dirty checkout contaminates a release artifact;
- table state is committed without the host's atomic compare-and-swap; or
- telemetry captures raw player, campaign, source, ruling, or exception text.

The full machine identities and correction rules live in
`docs/release-contract.md`; product invariants live in
`docs/product-truths.md`.
