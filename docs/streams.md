# Streams Reference

## Stream Summary

| Stream Name | Class | Base Class | Replication | Primary Keys | Replication Key |
|---|---|---|---|---|---|
| `adaccounts` | AdAccountsStream | FacebookStream | Incremental | created_time | created_time |
| `ads` | AdsStream | IncrementalFacebookStream | Incremental | id, updated_time | updated_time |
| `adsets` | AdsetsStream | IncrementalFacebookStream | Incremental | id, updated_time | updated_time |
| `campaigns` | CampaignStream | IncrementalFacebookStream | Incremental | id, updated_time | updated_time |
| `creatives` | CreativeStream | AccountLevelStream | Incremental | (none declared) | id |
| `adlabels` | AdLabelsStream | AccountLevelStream | Incremental | id, updated_time | updated_time |
| `adimages` | AdImages | AccountLevelStream | Incremental | (none declared) | id |
| `advideos` | AdVideos | AccountLevelStream | Incremental | (none declared) | id |
| `customaudiences` | CustomAudiences | AccountLevelStream | Full | id | -- |
| `customconversions` | CustomConversions | AccountLevelStream | Incremental | id | creation_time |
| `adsinsights_{name}` | AdsInsightStream | Stream (core) | Incremental | date_start, account_id, ad_id + breakdowns | date_start |

---

## AdAccountsStream

**File**: `tap_facebook/streams/ad_accounts.py`
**API Endpoint**: `GET /{api_version}/me/adaccounts`

The root parent stream. All other streams are children of this one and receive `account_id` through the parent-child context mechanism.

**Key behaviors**:

- Fetches all ad accounts accessible by the authenticated user.
- Passes requested `fields` as a query parameter built from the `columns` property (approximately 70 fields covering account info, agency declarations, business manager details, and extended credit info).
- `post_process()` casts `amount_spent`, `balance`, `min_campaign_group_spend_cap`, and `spend_cap` from strings to integers.
- `configured_location_ids` parses the `locations` config, supporting both the new format (list of `{"id": "...", "name": "..."}` objects) and legacy formats (list of strings, comma-separated string). Strips `act_` prefixes.
- `get_records()`: When the stream itself is deselected but locations are configured, it yields minimal `{"account_id": id}` records so child streams still receive context.
- `_sync_children()`: Skips child syncs for accounts not in the configured `locations` list.

---

## AdsStream

**File**: `tap_facebook/streams/ads.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/ads`

Fetches individual ad objects. Uses `IncrementalFacebookStream` which applies server-side filtering via the `filtering` parameter using `updated_time` as a UNIX timestamp with `GREATER_THAN` operator.

**Fields include**: id, account_id, adset_id, campaign_id, status, name, effective_status, creative (nested object with creative_id), tracking_specs (complex nested array), recommendations, configured_status, conversion_domain.

**Filter entity**: `ad`

---

## AdsetsStream

**File**: `tap_facebook/streams/adsets.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/adsets`

Fetches ad sets (campaign-level groupings). Uses `IncrementalFacebookStream` for server-side timestamp filtering.

**Fields include**: id, account_id, campaign_id, name, status, effective_status, daily_budget, lifetime_budget, budget_remaining, bid_amount, bid_strategy, targeting (complex nested object with geo_locations, demographics, audiences), promoted_object, attribution_spec, learning_stage_info.

**Filter entity**: `adset`

---

## CampaignStream

**File**: `tap_facebook/streams/campaign.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/campaigns`

Fetches campaigns. Uses `IncrementalFacebookStream`.

**Fields include**: id, account_id, name, objective, status, effective_status, buying_type, daily_budget, lifetime_budget, budget_remaining, spend_cap, bid_strategy, start_time, stop_time, special_ad_categories, pacing_type, boosted_object_id, adlabels (nested).

**Filter entity**: `campaign`

`post_process()` casts `daily_budget` to integer.

---

## CreativeStream

**File**: `tap_facebook/streams/creative.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/adcreatives`

Fetches ad creatives. Extends `AccountLevelStream` directly (no server-side incremental filtering).

**Fields include**: id, account_id, name, body, title, image_url, image_hash, video_id, link_url, call_to_action_type, object_story_spec, asset_feed_spec, thumbnail_url, instagram_permalink_url, platform_customizations, template_url_spec (nested with per-platform config for android/ios/web/windows_phone).

Uses `id` as replication key.

---

## AdLabelsStream

**File**: `tap_facebook/streams/ad_labels.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/adlabels`

Fetches ad labels associated with the account. Simple schema: id, account (nested object), created_time, updated_time, name.

---

## AdImages

**File**: `tap_facebook/streams/ad_images.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/adimages`

Fetches ad images. Fields include dimensions (height, width, original_height, original_width), hash, URLs (url, url_128, permalink_url), status, and associated creatives list.

---

## AdVideos

**File**: `tap_facebook/streams/ad_videos.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/advideos`

Fetches ad videos. Fields include metadata (title, description, length, views, post_views), status info, format array, embed_html, privacy settings, crossposting flags, and live_status.

---

## CustomAudiences

**File**: `tap_facebook/streams/custom_audiences.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/customaudiences`

Fetches custom audiences. No replication method set (defaults to full table). Overrides `get_url_params()` to exclude the `fields` parameter from the URL params since fields are included in the path.

**Fields include**: id, account_id, name, approximate_count (lower/upper bounds), customer_file_source, data_source, delivery_status, description, lookalike_spec (nested), is_value_based, retention_days, subtype.

---

## CustomConversions

**File**: `tap_facebook/streams/custom_conversions.py`
**API Endpoint**: `GET /{api_version}/act_{account_id}/customconversions`

Fetches custom conversion definitions. Simple schema: id, account_id, name, creation_time, business (object), is_archived, is_unavailable, last_fired_time.

---

## AdsInsightStream

**File**: `tap_facebook/streams/ad_insights.py`
**API Endpoint**: Facebook Batch API (`POST /`) wrapping `GET /act_{account_id}/insights`

This is the most complex stream in the tap. It does NOT extend RESTStream -- it extends `singer_sdk.streams.core.Stream` directly and manages its own HTTP interactions using the `facebook-business` Python SDK.

### How It Works

1. **Initialization**: Each insight report definition (from config `insight_reports_list` plus a built-in "default") produces a separate stream instance named `adsinsights_{report_name}`.

2. **Client setup**: `_initialize_client()` calls `FacebookAdsApi.init()` with the access token, timeout of 300s, and configured API version. Fetches the `AdAccount` object.

3. **Date range calculation**:
   - Start date is the later of: config `start_date`, the bookmark minus `lookback_window` days, or `oldest_allowed_start_date` (36 months ago, since Facebook stores metrics for max 37 months).
   - `_get_earliest_record_date()` makes a single Insights API call with `sort=created_time_ascending` to find the first date with actual data, avoiding wasted requests on empty date ranges.
   - End date is `end_date` from config or today.

4. **Batch request construction**: Iterates from start to end date in steps of `time_increment_days`. Builds batches of up to `BATCH_SIZE` (30) individual insight queries, each requesting a single time-increment window.

5. **Batch execution**: Sends the batch via `POST /` using the Facebook SDK. Each batch item is a `GET act_{account_id}/insights` with parameters for level, breakdowns, action_breakdowns, attribution windows, fields, and time_range.

6. **Response processing**: Iterates through batch responses. Successful items (code 200) have their data yielded as records. Failed items trigger individual retry logic.

7. **Retry on failure**: Failed batch items (rate limits `#80000`, 500 errors, "too many calls" 400s) are retried individually via `_execute_single_request_with_retries()` with exponential backoff starting at 60 seconds, up to 5 attempts.

### Rate Limiting

Before each batch execution, `check_limit()` calls `get_limit()` which:
- Makes a lightweight GET to the insights endpoint
- Reads the `x-business-use-case-usage` header
- Extracts `call_count`, `total_cputime`, and `total_time` percentages
- If the maximum of these exceeds `USAGE_LIMIT_THRESHOLD` (75%), sleeps for 5 minutes

### Schema Generation

The schema is dynamically built from `AdsInsights._field_types` metadata in the `facebook-business` SDK:
- `string` fields become `th.StringType`
- `list<AdsActionStats>` becomes an array of objects with all `AdsActionStats.Field` properties
- `list<AdsHistogramStats>` becomes an array of objects with string and integer-array properties
- Breakdown fields (from the report definition) are appended as `StringType` properties

### Primary Keys

Dynamic based on report definition: `["date_start", "account_id", "ad_id"]` plus any configured `breakdowns`.

### Default Columns

The default column list includes: ad_id, account_id, date_start, ad_name, adset_id, campaign_id, campaign_name, clicks, conversions, cpc, cpm, cpp, created_time, date_stop, impressions, reach, spend, updated_time, actions, action_values, conversion_values.

### Constants

| Constant | Value | Purpose |
|---|---|---|
| `BATCH_SIZE` | 30 | Max requests per batch API call |
| `USAGE_LIMIT_THRESHOLD` | 75 | Percentage threshold for proactive rate limit cooldown |
| `BACKOFF_MAX_RETRIES` | 5 | Max retry attempts for individual failed batch items |
| `BACKOFF_INITIAL_SLEEP` | 60 | Initial backoff sleep in seconds |
| `SLEEP_TIME_INCREMENT` | 5 | (Defined but not currently used in main flow) |
| `INSIGHTS_MAX_WAIT_TO_START_SECONDS` | 300 | (Defined but not currently used in main flow) |
| `INSIGHTS_MAX_WAIT_TO_FINISH_SECONDS` | 1800 | (Defined but not currently used in main flow) |
