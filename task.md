# Task: Upgrade Facebook Marketing API Version from v21 to v25

## Problem
Facebook Marketing API v21 is deprecated and will stop accepting requests. The tap currently defaults to `v21.0` and the `facebook-business` Python SDK is pinned to `^21.0.0`. We need to upgrade to a supported API version — ideally **v25**, minimum **v24**.

## Scope of Changes

### 1. Update `facebook-business` SDK dependency
- **File**: `pyproject.toml` (line 20)
- **Current**: `facebook-business = "^21.0.0"`
- **Target**: `facebook-business = "^25.0.0"` (or latest stable)
- **Action**: Update version pin, run `poetry lock` and `poetry install`

### 2. Update default `api_version` config value
- **File**: `tap_facebook/tap.py` (line 75)
- **Current**: `default="v21.0"`
- **Target**: `default="v25.0"`

### 3. Update fallback `api_version` in AdAccountsStream
- **File**: `tap_facebook/streams/ad_accounts.py` (line 35)
- **Current**: `version = self.config.get("api_version") or "v21.0"`
- **Target**: `version = self.config.get("api_version") or "v25.0"`

### 4. Validate field compatibility with v25
The Facebook Marketing API occasionally deprecates or renames fields between versions. The following need to be checked against the v25 API reference:

- **AdAccountsStream** (`ad_accounts.py`) — large column list (lines 41–121) and schema
- **AdsStream** (`ads.py`) — `columns` list includes `bid_type`, `bid_info`, `conversion_domain` which have been deprecated in past versions
- **CampaignStream** (`campaign.py`) — `columns` list includes `has_secondary_skadnetwork_reporting`, `is_skadnetwork_attribution`, `primary_attribution` (SKAdNetwork fields may have changed)
- **AdsInsightStream** (`ad_insights.py`) — `COLUMN_LIST` and SDK field references (`AdsInsights._field_types`, `AdsActionStats.Field`, `AdsHistogramStats.Field`)
- **AdsetsStream**, **CreativeStream**, **AdLabelsStream**, **AdImages**, **AdVideos**, **CustomAudiences**, **CustomConversions** — review columns/fields

### 5. Update `meltano.yml` default
- **File**: `meltano.yml` (line 26)
- **Current**: `value: 'v16.0'` (stale, already out of date)
- **Target**: `value: 'v25.0'`

### 6. Test
- Run `poetry run pytest` with valid credentials against the new API version
- Verify all streams still produce data
- Check for any new required fields or breaking schema changes

## Breaking Change Risks
- Fields removed in v25 will cause 400 errors when requested
- The `facebook-business` SDK version must match the API version — SDK v25 maps to API v25
- `AdsInsightStream` uses internal SDK types (`AdsInsights._field_types`) that may have changed
- Rate limit header format could change (unlikely but worth verifying)
- Batch API behavior in `ad_insights.py` should be tested

## Reference
- [Facebook Marketing API Changelog](https://developers.facebook.com/docs/graph-api/changelog)
- [facebook-business SDK on PyPI](https://pypi.org/project/facebook-business/)
