# Changelog

All notable changes to `tap-facebook-ads` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] - 2026-03-17

### Fixed — HotGlue Production Deployment
- **OAuth2Authenticator ported from hotglue/tap-facebook**: Added `tap_facebook/auth.py` with token refresh via `fb_exchange_token` grant and config file write-back. Replaces `BearerTokenAuthenticator` which didn't support HotGlue's OAuth flow.
- **`AttributeError: can't set attribute 'auth_headers'`**: singer-sdk v0.53 changed `auth_headers` from a property to a plain instance attribute. Moved token injection logic from `@property` override to `__call__()` method.
- **`KeyError: 'access_token'`** during config validation: Removed `required=True` from `access_token` in config schema — HotGlue manages OAuth tokens externally and may not have them at validation time.
- **`KeyError: 'access_token'`** at runtime: Tenants without OAuth credentials (`client_id`/`client_secret`) were triggering token refresh unnecessarily. Added `_can_refresh` guard — bearer-only configs now skip refresh and use the token as-is.
- **`KeyError: 'expires_in'`** in token refresh response: `update_access_token()` assumed Facebook always returns `expires_in` in the token exchange response. Now handled as optional.
- **`400 Bad Request` on token refresh**: Expired tokens can't be exchanged via `fb_exchange_token`. Refresh is now only attempted when `_can_refresh` is True and token is approaching expiry.
- **`TypeError: unexpected keyword argument 'setup_mapper'`**: `TapFacebook.__init__` override used explicit params that didn't include singer-sdk v0.53's new `setup_mapper` kwarg. Changed to `**kwargs` for forward compatibility.

### Added
- `tap_facebook/auth.py` — OAuth2Authenticator with dual-mode support (bearer-only and full OAuth)
- `backoff` as explicit dependency (used by auth.py retry logic)
- `docs/troubleshooting-steps.md` — production debugging guide with HotGlue-specific patterns
- `.claude/skills/python-dev.md` — separated Python tooling from Meltano skill
- `docs/schema-changes-v25.md` — downstream impact assessment for field removals/renames

### Changed
- `tap.py` — Added `__init__` override to capture `config_file` path for OAuth token write-back (HotGlue convention)
- `client.py` — Switched from `BearerTokenAuthenticator` to `OAuth2Authenticator`
- Python version constraint changed from `>=3.10` to `>=3.10,<4.0` (required by `backoff`)
- `.env.template` — Reduced to only the two actually-required env vars

---

## [Unreleased] - 2026-03-16

### Fixed
- **SECURITY**: Moved access_token from URL query string to Authorization header in rate limit check
- Non-retryable batch failures now raise `RuntimeError` instead of silently dropping data
- Non-rate-limit 4xx errors now raise `FatalAPIError` instead of silently skipping (supports HotGlue auto-rollback on failure)
- Added `sort=asc` and `order_by` params to incremental streams for reliable bookmark ordering
- Declared `access_token` as required config property in `config_jsonschema` (was used but not declared)
- `start_date` now falls back to oldest allowed date (37 months) when omitted, instead of crashing
- Fixed bare `raise e` to `raise` in `_get_earliest_record_date` to preserve tracebacks
- Added 30-second timeout to rate limit check HTTP request
- Removed duplicate `daily_budget` property in CampaignStream schema
- Removed duplicate `geo_locations` property in AdsetsStream targeting schema
- Fixed `selected == False` identity comparison to `not self.selected` in AdAccountsStream
- **BUG**: Fixed fields serialization across all streams — was sending Python list repr `"['field1', ...]"` instead of comma-separated `"field1,field2"` to the API
- Removed 5 fields from CreativeStream that were removed in API v25: `effective_instagram_story_id`, `instagram_story_id`, `instagram_actor_id`, `page_link`, `page_message`
- Replaced `instagram_actor_id` with `instagram_user_id` in CreativeStream (v22+ migration)
- Split CI into lint (runs on PRs) and integration-test (workflow_dispatch only) jobs
- Tests no longer crash when API credentials are missing — integration tests skip gracefully
- Added unit tests for stream discovery, default API version, and optional start_date

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
- `.claude/agents/etl-reliability.md` agent for ETL reliability audits
- `.claude/skills/etl-reliability.md` ETL reliability patterns and checklist
- `.claude/skills/data-quality.md` data quality validation patterns
- `pendulum` as explicit dependency (was implicit via older singer-sdk)

### CI
- Bumped `actions/checkout` from 4.1.1 to 6.0.0
- Bumped `actions/setup-python` from 5.1.0 to 6.0.0
- Bumped `actions/download-artifact` from 4.1.1 to 6.0.0
- Bumped `pypa/gh-action-pypi-publish` from 1.8.11 to 1.13.0
- Bumped `nox` from 2023.4.22 to 2025.10.16 in CI constraints
- Bumped `nox-poetry` from 1.0.3 to 1.2.0 in CI constraints
- Bumped `pip` from 23.3.2 to 25.3 in CI constraints
- Bumped `poetry` from 1.7.1 to 2.2.1 in CI constraints
- Bumped `poetry-dynamic-versioning` from 1.2.0 to 1.9.1 in CI constraints
- Updated Python test matrix from [3.9, 3.10, 3.11, 3.12] to [3.10, 3.11, 3.12, 3.13]
