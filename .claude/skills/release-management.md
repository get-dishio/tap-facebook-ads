---
name: release-management
description: Semantic versioning, release workflow, changelog management, and version tagging for tap-facebook-ads. Use when cutting releases, bumping versions, or deciding version numbers.
---

# Release Management

## Versioning Strategy

This project uses [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

| Component | When to increment | Examples |
|-----------|-------------------|----------|
| **MAJOR** (X.0.0) | Breaking changes that require downstream migration — removed/renamed fields, changed config schema, dropped Python versions, API version upgrades that alter output | 1.0.0 → 2.0.0: Remove a stream or change its primary key |
| **MINOR** (0.X.0) | New features, new streams, new config options, new fields added to existing streams — backward compatible | 1.0.0 → 1.1.0: Add a new stream or config option |
| **PATCH** (0.0.X) | Bug fixes, dependency updates, performance improvements, documentation — no schema or behavior changes visible to consumers | 1.0.0 → 1.0.1: Fix rate limiting, update a dependency |

### Version 1.0.0 Criteria

The tap is ready for 1.0.0 when:
- [ ] All streams sync successfully against the live Facebook Marketing API
- [ ] No SYNC_FAILED errors in HotGlue production for 24+ hours
- [ ] OAuth authenticator works for both bearer-only and full-OAuth tenants
- [ ] All unit tests pass (`poetry run pytest`)
- [ ] All lint checks pass (`poetry run ruff check .`)
- [ ] Schema changes documented in `docs/schema-changes-v25.md`
- [ ] CHANGELOG is up to date

### What constitutes a breaking change (MAJOR bump)?

- Removing a field from a stream schema (downstream tables lose a column)
- Renaming a field (e.g., `instagram_actor_id` → `instagram_user_id`)
- Changing a field's type (e.g., string → integer)
- Removing a stream entirely
- Changing primary keys or replication keys
- Changing config property names or removing config options
- Upgrading the Facebook API version if it changes output schema
- Raising the minimum Python version

### What is NOT a breaking change?

- Adding new fields to existing streams (additive)
- Adding new streams
- Adding new config options with defaults
- Fixing bugs (even if the "fix" changes behavior — the old behavior was wrong)
- Internal refactoring that doesn't change output
- Dependency updates that don't affect output

## How Versions Are Managed

This project uses `poetry-dynamic-versioning` which derives versions from git tags:

```toml
[tool.poetry-dynamic-versioning]
enable = true
```

- Version in `pyproject.toml` is always `0.0.0` (placeholder)
- Actual version comes from the most recent git tag
- `poetry run tap-facebook --about` shows `[could not be detected]` locally because there's no tag — this is normal

## Release Workflow

### 1. Verify readiness

```bash
# All tests pass
poetry run pytest -v

# All lint passes
poetry run ruff check .

# Discovery works
poetry run tap-facebook --config .secrets/config.json --discover > /dev/null

# Check HotGlue production — no SYNC_FAILED for this tap
```

### 2. Update CHANGELOG

Move the `[Unreleased]` section to a versioned section:

```markdown
## [1.0.0] - 2026-03-18

### Changed
- ...
```

Keep an empty `[Unreleased]` section at the top for future changes.

### 3. Commit the CHANGELOG

```bash
git add CHANGELOG.md
git commit -m "Release v1.0.0"
```

### 4. Tag the release

```bash
git tag -a v1.0.0 -m "v1.0.0 — Facebook Marketing API v25 upgrade"
git push origin v1.0.0
```

The `release.yaml` GitHub Action will automatically:
- Build the Python package
- Upload the wheel to the GitHub release
- Publish to PyPI (if configured)

### 5. Merge to main

```bash
git checkout main
git merge stage
git push origin main
```

### 6. Update HotGlue connector entity

Update the `install_uri` in the HotGlue connector entity to point to the tag instead of the branch:

```
git+https://github.com/get-dishio/tap-facebook-ads.git@v1.0.0
```

This pins production to the release tag instead of a moving branch head.

## Branch Strategy

| Branch | Purpose | HotGlue points to |
|--------|---------|-------------------|
| `main` | Stable, release-ready code | Production (via tags) |
| `stage` | Integration testing in HotGlue | `@stage` for pre-release testing |
| `fb-marketing-api-v25-upgrade` | Feature branch (merged to stage) | — |

## Deciding the Version Number

Ask these questions in order:

1. **Did any stream schema change?** (fields removed, renamed, type changed, primary key changed)
   → **MAJOR** bump. Document in `docs/schema-changes-v25.md`.

2. **Did any new stream or config option get added?**
   → **MINOR** bump.

3. **Everything else** (bug fixes, dep updates, docs, internal refactoring)
   → **PATCH** bump.

### Special case: first stable release

If no prior version tag exists, the first release should be `1.0.0` once the tap is production-stable. Pre-release versions (`0.x.y`) indicate the tap is not yet production-ready.

## Post-Release Checklist

- [ ] Tag pushed to GitHub
- [ ] GitHub release created (automatic via `release.yaml`)
- [ ] CHANGELOG updated with version and date
- [ ] HotGlue connector entity `install_uri` updated to tag
- [ ] Downstream consumers notified of breaking changes (if MAJOR bump)
- [ ] Monitor HotGlue production for 24 hours after release
