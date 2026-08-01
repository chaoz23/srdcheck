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

# 6. Tag; CI publishes from the clean commit.
git tag vX.Y.Z && git push --tags
```

## Acceptance before publishing

- [ ] `pytest tests/` green on Python 3.10–3.13
- [ ] `tests/test_packaging.py` green — wheel carries `sources/text/*.txt`
      and `cite` works from a cold install, outside the repo, offline
- [ ] `tests/test_metadata_fresh.py` green — every surface reports one version
- [ ] `scripts/check_repo_hygiene.py` exits 0
- [ ] `NOTICE` ships in the wheel metadata
