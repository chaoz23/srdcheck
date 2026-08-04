# Incident response

This runbook covers deterministic ruling defects, privacy exposure,
supply-chain compromise, and release/registry failure. SRDCheck is alpha and
has no staffed 24/7 response function; record the real responder and timeline.

## Severity

- **S1:** malicious release, credential compromise, unlicensed/private content
  shipped, or a wrong ruling likely to corrupt persisted table state.
- **S2:** reproducible wrong ruling, broken public artifact, privacy-safe trace
  contract violation, or current-release registry identity mismatch.
- **S3:** localized tooling/documentation defect with a safe workaround.

## First response

1. Preserve public evidence: version, adapter/data/rules tuple, verdict ID,
   request shape with secrets removed, artifact hash, and workflow/run URL.
2. Do not request raw campaign logs, prompts, private table state, credentials,
   or commercial rulebook text in a public issue.
3. Contain without rewriting history: stop a pending publish, disable a host
   sink, revoke compromised credentials, or yank an unusable PyPI version.
   Never move or silently replace a published tag.
4. Assign one incident lead, one rules/security reviewer, severity, impact,
   status, and next update time.

## Ruling defect

Reproduce against the exact release tuple from `srdcheck capabilities`. Decide
whether the failure is bad input, coverage overclaim, engine defect, adapter
data defect, or adapter rule defect. Add a failing focused test before the fix.
Every corrected ruling follows `docs/release-contract.md` and updates
`docs/ruling-corrections.json`; high/critical corrections require a public
notice and explicit caller action. Do not regenerate goldens to bless a change.

## Privacy or telemetry exposure

Disable the affected host sink while leaving verdict execution available.
Determine whether parameters, prompts, table state/decisions, citations/source
text, `why`, exception messages, or caller identities escaped. The host owns
access, retention, deletion, participant notification, and legal obligations;
SRDCheck itself has no event store. Add a seeded secret-exclusion regression
before restoring telemetry.

## Supply chain or credential compromise

Revoke the affected GitHub/PyPI/OAuth session, review Actions/environment and
trusted-publisher changes, compare the tag commit, artifact checksums, SBOM,
and GitHub provenance, and block publication until two people review the
result. Preserve compromised artifacts for analysis; do not delete evidence.

## Registry or release mismatch

Stop before publishing the next surface. Verify, in order: annotated tag to
commit, project/server metadata, tagged artifact run, attestation, PyPI wheel
and sdist, GitHub Release, then MCP Registry. A delayed index is not fixed by
rebuilding; retry the public smoke against the same immutable artifacts.

## Closure record

Record detection, severity, affected versions/tables, containment, root cause,
corrective tests, release/correction notice, deletion/notification actions,
and follow-up owner/date. Close only after public-artifact verification.
