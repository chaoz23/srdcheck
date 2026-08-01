# Releasing srdcheck

## Rules

1. **Version lives in exactly one place:** `version` in `pyproject.toml`.
   `srdcheck.__version__`, the MCP `serverInfo`, and `tool.json` all derive
   from it. Never add a second version literal — 0.5.0 shipped a package at
   `0.5.0` whose MCP server announced itself as `0.2.0`.
   Ruleset/adapter versions are *separate* and live in each adapter manifest.

2. **Generated artifacts are never committed.** `build/`, `dist/`, and
   `*.egg-info/` are ignored and blocked by `scripts/check_repo_hygiene.py`.
   A stale `build/lib/` silently masks packaging bugs: setuptools reuses it, so
   a wheel built in a dirty tree can contain files a fresh clone would omit.
   That is how the 0.5.0 wheel passed locally and shipped broken.
   **Always `rm -rf build dist *.egg-info` before building a release.**

3. **Only CC-BY SRD content is redistributed.** See `NOTICE`. No commercial
   adventures, rulebooks, or other non-SRD publications may ever be tracked.

## Cutting a release

```bash
# 1. Clean the tree — non-negotiable, see rule 2.
rm -rf build dist src/*.egg-info srdcheck.egg-info

# 2. Bump the single version source.
$EDITOR pyproject.toml          # version = "X.Y.Z"

# 3. Regenerate derived metadata.
python3 scripts/gen_tool_json.py

# 4. Full gates, including the cold-install journeys.
python3 scripts/check_repo_hygiene.py
python3 -m pytest tests/ -q

# 5. Build and verify the artifact, not the checkout.
python3 -m build
python3 -m pytest tests/test_packaging.py -q

# 6. Commit the reviewed release diff on a branch and merge it through a PR.
git status --short                 # inspect the exact release diff
git add -u
git commit -m "Release vX.Y.Z"
git push -u origin release/vX.Y.Z

# After the PR is green and merged, update and prove a clean main checkout.
git switch main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

# 7. Tag; CI builds, cold-tests, checksums, SBOMs, and attests the commit.
git tag -a vX.Y.Z -m "srdcheck vX.Y.Z"
git push origin refs/tags/vX.Y.Z

# 8. After release-artifacts is green, explicitly dispatch the trusted PyPI
#    publisher with that tag workflow's run ID. This rebuilds nothing: it
#    downloads and checksum-verifies the exact CI artifacts before upload.
gh workflow run publish-pypi.yml \
  --ref main \
  -f version=X.Y.Z \
  -f artifact_run_id=TAG_WORKFLOW_RUN_ID

# 9. Publish the GitHub release only after PyPI shows both files. That event
#    starts registry-smoke against the exact public version.
gh release create vX.Y.Z --verify-tag --generate-notes
```

## Acceptance before publishing

- [ ] Full Ubuntu `test` lanes green on Python 3.10–3.13
- [ ] `minimum-runtime` green on Python 3.10 with the declared build floor
- [ ] Windows and macOS `platform-smoke` lanes green under the documented
      [support contract](support-matrix.md)
- [ ] `cold-install` green for both wheel and source distribution on Python
      3.10 and 3.13
- [ ] `tests/test_packaging.py` green — wheel carries `sources/text/*.txt`
      and `cite` works from a cold install, outside the repo, offline
- [ ] `tests/test_metadata_fresh.py` green — every surface reports one version
- [ ] `scripts/check_repo_hygiene.py` exits 0
- [ ] `NOTICE` ships in the wheel metadata
