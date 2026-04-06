# Troubleshooting Guide

Common issues encountered when running `tap-facebook-ads` via HotGlue, with root causes and resolutions.

---

## HotGlue Deployment Issues

### `'access_token' is a required property` — Config Validation Failed

**Symptoms**: Discovery succeeds (with a warning), but sync fails immediately with:
```
ERROR | tap-facebook | 'access_token' is a required property
ERROR | tap-facebook | Config validation failed
```

**Root Cause**: The `access_token` property was marked `required=True` in the tap's `config_jsonschema`. HotGlue manages OAuth tokens externally and may inject them into config under timing that doesn't align with strict validation.

**Resolution**: Never mark `access_token` as `required` in the JSON schema. Declare it as optional (`secret=True` only) — the authenticator will fail with a clear error at runtime if the token is actually missing.

**Commit**: `7d7a239` — Remove required=True from access_token config property

---

### `KeyError: 'access_token'` — Token Not in Config

**Symptoms**: Sync starts, streams are added, but the first API call fails with:
```
ERROR | tap-facebook.adaccounts | An unhandled error occurred while syncing 'adaccounts'
ERROR | tap-facebook            | access_token
KeyError: 'access_token'
```
The traceback points to `client.py` in the `authenticator` property.

**Root Cause**: The config.json delivered by HotGlue doesn't contain an `access_token` key. This happens when:
1. The tenant's OAuth connection has expired or was never completed
2. The tap is using `BearerTokenAuthenticator` (static token) instead of `OAuth2Authenticator` (which can refresh tokens)
3. HotGlue's OAuth flow failed silently and didn't persist the token

**Resolution**: Port the `OAuth2Authenticator` from the [hotglue/tap-facebook](https://github.com/hotgluexyz/tap-facebook) convention:
- `tap_facebook/auth.py` handles token refresh via `fb_exchange_token` grant
- `client.py` uses `OAuth2Authenticator` instead of `BearerTokenAuthenticator`
- `tap.py` overrides `__init__` to capture `config_file` path for write-back

**How to verify**: Check the tenant's config.json in HotGlue (S3 or dashboard). If `access_token` is missing entirely, the OAuth connection needs to be re-established through the HotGlue widget.

**Commit**: `e0b37ad` — Port OAuth2Authenticator from hotglue tap-facebook convention

---

### `Config validation failed` (WARNING during discovery)

**Symptoms**: Discovery log shows:
```
WARNING | tap-facebook | Config validation failed
```
But discovery completes successfully and uploads the catalog.

**Root Cause**: The Singer SDK validates config against `config_jsonschema` and logs a warning for any validation errors. During discovery, this is non-fatal. Common triggers:
- Extra keys in config that aren't in the schema (e.g., `client_id`, `client_secret`, `user_agent`)
- Missing optional properties that have no default

**Resolution**: This warning is harmless during discovery. If it causes issues during sync, check that the config keys match what the tap expects. The tap's schema should be permissive enough to accept HotGlue's config format (which often includes extra OAuth fields).

---

## Facebook API Issues

### `400 Client Error: too many calls` / `request limit reached`

**Symptoms**: REST streams fail with 400 errors containing rate limit messages.

**Root Cause**: Facebook Marketing API rate limits are per-ad-account and based on call count, CPU time, and total time.

**Resolution**: The tap handles this automatically:
- REST streams: `validate_response()` raises `RetriableAPIError`, triggering exponential backoff (up to 20 retries)
- Insights stream: `check_limit()` proactively checks `x-business-use-case-usage` header and sleeps 5 minutes when usage exceeds 75%
- Batch API: Individual failed items are retried with `_execute_single_request_with_retries()` (5 retries, 60s initial backoff, doubling)

**If it persists**: The account may be hitting hard limits. Reduce sync frequency or narrow the date range via `start_date`/`end_date`.

---

### `500 Server Error` on specific streams

**Symptoms**: Intermittent 500 errors from the Facebook API, typically on large ad accounts or creatives with many records.

**Root Cause**: Facebook's backend occasionally returns transient 500 errors under load.

**Resolution**: The tap automatically retries 500 errors:
- REST streams: `RetriableAPIError` with backoff
- Batch API: Falls back to `_execute_single_request_with_retries()` for the failed item

These are normal and self-resolve. Check the logs — you should see "Backing off" messages followed by successful retries.

---

### `No data exists for this account in the specified date range`

**Symptoms**: Insights stream logs this message and yields no records for an account.

**Root Cause**: The account genuinely has no ad data in the requested date range, OR `start_date` is set to a date after the account's actual data.

**Resolution**:
- If `start_date` is omitted, the tap falls back to 37 months ago (Facebook's maximum)
- Check if the ad account actually has active campaigns in the expected date range
- The tap calls `_get_earliest_record_date()` to optimize the start date — if the API returns no data for the full range, there's nothing to sync

---

### Token Expiration — `OAuthException` or `Error validating access token`

**Symptoms**: API calls fail with authentication errors after a period of working correctly.

**Root Cause**: Facebook access tokens have limited lifetimes:
- Short-lived tokens: ~1 hour
- Long-lived tokens: ~60 days
- The `OAuth2Authenticator` in `auth.py` refreshes tokens 10 days before expiration

**Resolution**:
1. Verify `expires_at` is present in the tenant's config.json — without it, the authenticator can't determine when to refresh
2. Verify `client_id` and `client_secret` are present — these are required for the `fb_exchange_token` grant
3. If the token is already expired, the refresh will fail. The tenant needs to re-authenticate through the HotGlue widget
4. The connector entity has `no_refresh: True` — this means HotGlue itself doesn't refresh the token; the tap is responsible via `auth.py`

---

## Singer SDK / Dependency Issues

### `ModuleNotFoundError: No module named 'pendulum'`

**Root Cause**: `pendulum` was a transitive dependency of older `singer-sdk` versions but is no longer bundled in v0.53+.

**Resolution**: Added `pendulum` as an explicit dependency in `pyproject.toml`. If you see similar errors for other modules, check if they're used directly in code but only available as transitive deps.

**Commit**: `7cc4c48` — Add pendulum as explicit dependency

---

### `Command not found: ruff` in CI

**Root Cause**: `ruff` was configured in `pyproject.toml` under `[tool.ruff]` but never listed as a dev dependency.

**Resolution**: Added `ruff >= 0.8.0` to `[tool.poetry.group.dev.dependencies]`.

**Commit**: `883ae6a` — Add ruff as dev dependency

---

### `DeprecationWarning: RESTStream.get_next_page_token is deprecated`

**Symptoms**: Warning in logs about `get_next_page_token` and `create_for_stream`.

**Root Cause**: Singer SDK v0.53 deprecated these in favor of `get_new_paginator` and direct authenticator construction.

**Resolution**: These are warnings only and don't affect functionality. They should be addressed in a future cleanup PR to use the new SDK patterns:
- Replace `get_next_page_token` with `get_new_paginator`
- Replace `BearerTokenAuthenticator.create_for_stream` with direct instantiation

---

## HotGlue Platform Behavior

### `The object does not exist` (WARNING)

**Symptoms**: HotGlue executor logs this warning during sync setup.

**Root Cause**: HotGlue is trying to download `state.json` for the tenant but no previous state exists (first sync). This is normal.

**Resolution**: No action needed. The tap starts a full sync when no state is available.

---

### Connector zip caching

HotGlue caches connector installations as zip archives in S3:
```
config/connector_zips/tap-facebook-ads_stage_<commit_hash>.3.10.zip
```

After pushing a new commit to the `stage` branch, HotGlue will build a new zip on the next discover/sync. You can verify the correct commit is running by checking the hash in the zip filename against `git log --oneline -1`.

---

### ETL script packages

HotGlue downloads transformation scripts from:
```
s3://prod.hg.dish.io:default/flows/<flow_id>/taps/facebook-v2/etl/
s3://prod.hg.dish.io:packages
```

If transformations fail, check that the ETL scripts are compatible with the new schema (see `docs/schema-changes-v25.md` for field removals and renames).

---

## Debugging Checklist

When a sync fails in HotGlue:

1. **Check the error type**:
   - Config validation → check config.json keys vs tap schema
   - KeyError → missing config key, check OAuth status
   - FatalAPIError → non-retryable API error, check the response body
   - RuntimeError → batch API failure or max retries exceeded

2. **Check the commit hash**: Match the connector zip hash to the expected branch HEAD

3. **Check the tenant's OAuth status**: Re-link the Facebook connection if token is missing/expired

4. **Check the catalog**: If discovery succeeded but sync fails on a specific stream, the catalog-selected.json may reference fields that no longer exist (see schema changes doc)

5. **Check state.json**: If the tap starts from an unexpected date, the bookmark in state.json may be stale. Clear it via HotGlue's API to force a full resync

6. **Run locally**: Use `.secrets/config.json` with the tenant's config to reproduce:
   ```bash
   poetry run tap-facebook --config .secrets/config.json --discover
   poetry run tap-facebook --config .secrets/config.json --catalog catalog-selected.json
   ```
