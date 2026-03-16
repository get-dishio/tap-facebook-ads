# Changelog

All notable changes to `tap-facebook-ads` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **BREAKING**: Upgraded Facebook Marketing API from v21 to v25
- **BREAKING**: Minimum Python version raised from 3.8 to 3.10
- Updated `facebook-business` SDK from `^21.0.0` to `^25.0.0`
- Updated `singer-sdk` from `>=0.27,<0.36` to `>=0.53,<0.54`
- Updated `requests` from `~=2.31.0` to `~=2.32.0`
- Updated `pytest` from `>=7.4.1` to `>=9.0.0`
- Updated `poetry-core` from `1.8.1` to `>=2.0,<3.0`
- Updated `poetry-dynamic-versioning` from `1.2.0` to `>=1.10,<2.0`
- Default `api_version` config changed from `v21.0` to `v25.0`
- Fixed stale `meltano.yml` api_version default (was `v16.0`, now `v25.0`)
- Migrated deprecated `[tool.poetry.dev-dependencies]` to `[tool.poetry.group.dev.dependencies]`

### Removed
- Removed deprecated `bid_type` field from Ads stream (removed in API v25)
- Removed deprecated `bid_info` field from Ads stream (removed in API v25)
- Removed deprecated `bid_amount` field from Ads stream (moved to AdSet level only)
- Removed deprecated `conversion_specs` field from Ads stream (not readable in API v25)
- Removed deprecated `salesforce_invoice_group_id` field from AdAccounts stream

### Added
- `CLAUDE.md` project documentation for AI-assisted development
- `task.md` upgrade task specification
- `CHANGELOG.md` (this file)
- `/docs/` folder with architecture, streams, configuration, and development guides
- `.claude/settings.json` with security best practices
- `.claude/agents/tap-developer.md` agent for tap development
- `.claude/skills/` with Meltano, Singer, and HotGlue skill definitions
