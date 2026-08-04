# Takeover and operational ownership

This is the acquisition and maintainer-handoff control document for SRDCheck.
It distinguishes repository evidence from human attestations. An unchecked item
is a real diligence gap; silence never means complete.

## Current accountable identities

The public repository verifies only that `@chaoz23` owns the GitHub repository,
is named in package author metadata, and operated the 2026-08-03 release. Other
historical Git author aliases remain unresolved; do not silently attribute
them or publish personal-identity correlations inferred from local metadata.

Before a transaction closes, a protected transaction-room ledger must map each
material alias to an accountable contributor and capture human attestation of
identity, capacity, and rights to contribute. Counsel must document any residual
risk. The public repository records completion status, not private identity or
contact evidence.

## Service and recovery inventory

| asset | current evidence | transfer/recovery action | drill status |
|---|---|---|---|
| GitHub repository and Actions | public repository owned by `@chaoz23`; live protection/security settings require private diligence | add successor admin, require PR checks/review, enable applicable security controls, verify recovery methods, then exercise a non-destructive admin recovery | not run |
| PyPI `srdcheck` | trusted publication through the GitHub `pypi` environment and `.github/workflows/publish-pypi.yml`; no package token is required by CI | add and verify at least two PyPI owners; transfer the trusted-publisher binding and recovery contacts; publish a drill release | not run |
| MCP Registry namespace | GitHub OAuth proves control of `io.github.chaoz23/srdcheck`; `server.json` is the checked-in declaration | verify successor GitHub identity can authenticate and publish an already-public package version in a rehearsal namespace or approved drill | current owner published 0.9.0; successor not run |
| GitHub release signing | GitHub Actions OIDC and build-provenance attestations; no project signing key found | successor verifies an attestation and runs the tagged build under least privilege | current pipeline proven; successor not run |
| source/license inputs | MIT code plus attributed CC-BY-4.0 SRD text; pinned source hashes and extraction checks | preserve `LICENSE`, `NOTICE`, adapter manifests, hashes, and provenance CI | automated on every full CI run |
| domains | no project-owned domain found in repository configuration | record “none” at close or add registrar/DNS recovery evidence | repository-only audit complete |
| analytics and table telemetry | SRDCheck has no network exporter or persistence; observability sinks belong to the host | inventory every deployment separately, including access, retention, export, and deletion | host-specific; out of repository scope |

Never put credentials, recovery codes, tokens, private table content, or personal
contact details in this file. Record only the custodian and where the protected
record is held.

## AI-assisted contribution inventory

Known evidence:

- OpenAI Codex assisted code, tests, documentation, release operations, and
  this operational audit under `@chaoz23` direction. PR #68 is a known example.
- No new independent benchmark gold was created in PR #68; its compatibility
  fixture records the exact prior public engine behavior.
- Historical AI-tool/model use for code, tests, benchmark golds, and prose was
  not recorded consistently and cannot be reconstructed from Git history.

Future PRs must disclose AI assistance by artifact class and name the human who
accepts responsibility. Tool output is never review evidence. Rule changes need
source/citation review; benchmark golds need independent DM review; code needs
tests and contract review; generated prose needs factual and link review.

## Required handoff packet

The outgoing maintainer supplies and the incoming maintainer verifies:

- [ ] private contributor alias/rights attestations and unresolved exceptions;
- [ ] GitHub admin, branch rules, Actions environments, and recovery access;
- [ ] two-owner PyPI access and trusted-publisher recovery;
- [ ] MCP Registry namespace publication by the successor;
- [ ] architecture, release, incident, and support runbooks in this repository;
- [ ] open issues, known rule corrections, unsupported scope, and security risks;
- [ ] a release drill recorded with immutable tag, workflow, package, and
      registry evidence; and
- [ ] named outgoing/incoming contacts and a support window of at least 30
      calendar days beginning on the documented transfer date.

## Thirty-day transition agreement template

This template is a minimum, not an automatically binding promise. The named
parties must accept it in the transaction record.

> From **[transfer date]** through **[date at least 30 calendar days later]**,
> **[outgoing accountable maintainer]** will provide best-effort operational
> clarification to **[incoming accountable maintainer]** for release,
> provenance, incident, registry, and support questions. Severity-1 security or
> wrong-ruling incidents use the contacts and response expectations agreed in
> the private transfer record. The outgoing maintainer is not required to add
> product scope or disclose third-party secrets.

## Second-maintainer release drill

The drill is incomplete until a person other than the current release operator:

1. starts from a clean checkout and reads `docs/RELEASE.md` without coaching;
2. verifies version/tag identity and runs the full local gates;
3. opens and merges a reviewed release PR under branch protection;
4. creates the annotated tag and verifies artifact hashes, SBOM, and provenance;
5. dispatches trusted PyPI publication and verifies wheel and sdist publicly;
6. publishes/verifies the matching MCP Registry declaration; and
7. records operator, date, commits, run URLs, failures, recovery actions, and
   elapsed hands-on time in the transfer record.

A rehearsal may use the next genuine release; do not publish a fake production
version merely to satisfy this checklist.

## Readiness status

The runbooks and inventory structure are present. Takeover is **not ready to
close** until contributor identity/rights, second-owner access, branch
protection, the 30-day agreement, and the second-maintainer release drill have
human evidence.
