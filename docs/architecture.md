# Architecture

## Overview

`tap-facebook-ads` is a Singer tap built with the [Meltano Singer SDK](https://sdk.meltano.com/) for extracting data from the Facebook Marketing API. It is deployed via HotGlue to replicate ad account data into the Dishio platform.

The tap fetches data from multiple Facebook Marketing API endpoints -- ad accounts, campaigns, ad sets, ads, creatives, insights, and more -- and outputs Singer-formatted messages (SCHEMA, RECORD, STATE) for downstream targets.

## Project Layout

```
tap_facebook/
  tap.py                          # TapFacebook class -- entry point, config schema, stream discovery
  client.py                       # FacebookStream -- REST base class (auth, pagination, error handling)
  streams/
    __init__.py                   # Re-exports all stream classes
    ad_accounts.py                # AdAccountsStream -- root parent, fetches /me/adaccounts
    base_streams.py               # AccountLevelStream, IncrementalFacebookStream -- shared base classes
    ad_insights.py                # AdsInsightStream -- SDK-based batch insights extraction
    ads.py                        # AdsStream
    adsets.py                     # AdsetsStream
    campaign.py                   # CampaignStream
    creative.py                   # CreativeStream
    ad_labels.py                  # AdLabelsStream
    ad_images.py                  # AdImages
    ad_videos.py                  # AdVideos
    custom_audiences.py           # CustomAudiences
    custom_conversions.py         # CustomConversions
tests/
  test_core.py                    # SDK standard test suite + unit tests
pyproject.toml                    # Poetry project config, dependencies, CLI entry points
meltano.yml                       # Meltano project definition
```

## Data Flow

```
1. TapFacebook.discover_streams()
   |
   +--> Instantiates all REST-based stream classes (STREAM_TYPES list)
   +--> Instantiates AdsInsightStream for each report in insight_reports_list
   |    (plus one "default" report that is always included)
   |
2. Singer SDK orchestrates sync
   |
   +--> AdAccountsStream fetches /me/adaccounts
   |    |
   |    +--> get_records(): If the stream itself is not selected but locations
   |    |    are configured, yields synthetic records with just account_id
   |    |    (so children still receive context)
   |    |
   |    +--> _sync_children(): Filters child syncs to only configured location IDs
   |    |
   |    +--> get_child_context(): Passes {"account_id": ...} to all children
   |
3. Child streams receive account_id via context
   |
   +--> REST children (ads, adsets, campaigns, etc.)
   |    Hit /act_{account_id}/{endpoint} via Graph API REST calls
   |
   +--> AdsInsightStream (non-REST)
        Uses facebook-business Python SDK for batch API requests
        Posts batches of 30 day-range insight queries to the Batch API
```

## Two Stream Architectures

The tap uses two fundamentally different approaches for data extraction:

### REST Streams (most endpoints)

Built on `singer_sdk.streams.RESTStream` via the `FacebookStream` base class in `client.py`.

- **Auth**: `BearerTokenAuthenticator` with the configured `access_token`
- **Base URL**: `https://graph.facebook.com/{api_version}`
- **Pagination**: Cursor-based using `$.paging.cursors.after` from response JSON
- **Page size**: 25 records per request
- **Error handling**: Retries on rate-limit 400s ("too many calls" / "request limit reached") and all 500-level errors; other 4xx errors are logged and skipped
- **Retry limit**: `backoff_max_tries = 20`

### SDK-Based Stream (AdsInsightStream only)

Built directly on `singer_sdk.streams.core.Stream` -- does NOT use RESTStream.

- **Client**: Initializes `FacebookAdsApi` from the `facebook-business` SDK per account
- **Batch API**: Sends up to 30 insight queries per batch via `POST /` to the Graph API Batch endpoint
- **Rate limiting**: Proactively checks `x-business-use-case-usage` header; sleeps 5 minutes when any metric (call_count, total_cputime, total_time) exceeds 75%
- **Retry**: Individual failed batch items are retried with exponential backoff (initial 60s, up to 5 retries)
- **Schema**: Dynamically built from `AdsInsights._field_types` SDK metadata, including nested `AdsActionStats` and `AdsHistogramStats` types

## Class Hierarchy

```
singer_sdk.streams.RESTStream
  +-- FacebookStream (client.py)
        +-- AdAccountsStream (ad_accounts.py)   -- root parent, /me/adaccounts
        +-- AccountLevelStream (base_streams.py) -- adds /act_{account_id} prefix
              +-- CreativeStream
              +-- AdLabelsStream
              +-- AdImages
              +-- AdVideos
              +-- CustomAudiences
              +-- CustomConversions
              +-- IncrementalFacebookStream (base_streams.py) -- adds replication key filtering
                    +-- AdsStream
                    +-- AdsetsStream
                    +-- CampaignStream

singer_sdk.streams.core.Stream
  +-- AdsInsightStream (ad_insights.py) -- standalone, uses facebook-business SDK
```

## Parent-Child Relationship

`AdAccountsStream` is the single parent stream. All other streams declare `parent_stream_type = AdAccountsStream` either directly or through the `AccountLevelStream` base class. The parent passes `{"account_id": record["account_id"]}` to children via `get_child_context()`.

When `locations` are configured, the parent's `_sync_children()` method filters child syncs so that only the specified ad account IDs are processed. If the parent stream itself is not selected in the catalog but children are, it yields minimal records containing just the `account_id` so that children still get their context.

## Key Dependencies

| Package | Purpose |
|---|---|
| `singer-sdk` (>=0.53,<0.54) | Singer tap framework, RESTStream base, state management |
| `facebook-business` (^25.0.0) | Facebook Marketing API SDK, used by AdsInsightStream for batch requests and schema metadata |
| `requests` (~=2.32.0) | HTTP client for REST streams |
| `pendulum` | Date/time handling throughout |
