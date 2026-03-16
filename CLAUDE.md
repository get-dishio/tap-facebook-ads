# tap-facebook-ads

Singer/Meltano tap for extracting data from the Facebook Marketing API, used via HotGlue to replicate ad data into the Dishio platform.

## Project Overview

- **Framework**: Built with the [Meltano Singer SDK](https://sdk.meltano.com) (`singer-sdk >=0.27,<0.36`)
- **Language**: Python (>=3.8)
- **Package Manager**: Poetry (with `poetry-dynamic-versioning`)
- **Facebook SDK**: `facebook-business` (currently `^21.0.0`)
- **API Version**: Configurable via `api_version` config, currently defaults to `v21.0`

## Architecture

### Entry Point
- `tap_facebook/tap.py` — `TapFacebook` class, defines config schema and discovers streams

### Client
- `tap_facebook/client.py` — `FacebookStream` (REST base class), constructs `graph.facebook.com/{api_version}` URLs, handles auth, pagination, error handling with backoff

### Streams
All streams live under `tap_facebook/streams/`:

| Stream | File | Type | Notes |
|---|---|---|---|
| `AdAccountsStream` | `ad_accounts.py` | REST (parent) | Root stream, provides `account_id` context to children. Supports location filtering. |
| `AdsStream` | `ads.py` | REST (incremental) | Child of AdAccounts |
| `AdsetsStream` | `adsets.py` | REST (incremental) | Child of AdAccounts |
| `CampaignStream` | `campaign.py` | REST (incremental) | Child of AdAccounts |
| `CreativeStream` | `creative.py` | REST | Child of AdAccounts |
| `AdLabelsStream` | `ad_labels.py` | REST | Child of AdAccounts |
| `AdImages` | `ad_images.py` | REST | Child of AdAccounts |
| `AdVideos` | `ad_videos.py` | REST | Child of AdAccounts |
| `CustomAudiences` | `custom_audiences.py` | REST | Child of AdAccounts |
| `CustomConversions` | `custom_conversions.py` | REST | Child of AdAccounts |
| `AdsInsightStream` | `ad_insights.py` | SDK-based (`facebook-business`) | Uses FB SDK directly, batch API, rate limit handling. Not a RESTStream. |

### Base Classes
- `tap_facebook/streams/base_streams.py` — `AccountLevelStream` (adds account path) and `IncrementalFacebookStream` (adds replication key filtering)

## Key Config Settings
- `access_token` — Facebook API token (required)
- `api_version` — Graph API version string, e.g. `v21.0` (default: `v21.0`)
- `locations` — List of `{"id": "...", "name": "..."}` objects to filter ad accounts
- `start_date` / `end_date` — Date range for syncing
- `insight_reports_list` — Custom insight report definitions (breakdowns, attribution windows, etc.)

## API Version References
The `api_version` config is used in:
1. `tap_facebook/tap.py:75` — default value `v21.0`
2. `tap_facebook/streams/ad_accounts.py:35` — fallback `v21.0`
3. `tap_facebook/client.py:28-29` — base URL construction
4. `tap_facebook/streams/ad_insights.py:135` — `FacebookAdsApi.init()`
5. `tap_facebook/streams/ad_insights.py:169` — direct URL construction
6. `tap_facebook/streams/ad_insights.py:426-427` — rate limit check URL

## Commands
```bash
# Install dependencies
poetry install

# Run tests (requires TAP_FACEBOOK_ACCESS_TOKEN and TAP_FACEBOOK_ACCOUNT_ID env vars)
poetry run pytest

# Run the tap
poetry run tap-facebook --config config.json --discover
poetry run tap-facebook --config config.json

# Lint
poetry run ruff check .
```

## Testing
Tests require live Facebook API credentials set as environment variables:
- `TAP_FACEBOOK_ACCESS_TOKEN`
- `TAP_FACEBOOK_ACCOUNT_ID`
