# Configuration Reference

## Required Settings

### `access_token`

**Type**: string (password)
**Required**: Yes

A Facebook Marketing API access token. Must have `ads_read` permission on the target ad accounts. Obtain from [Facebook Business Settings](https://business.facebook.com/settings) or via the OAuth flow in HotGlue.

This token is used in two ways:
- As a Bearer token in the `Authorization` header for REST stream requests
- Passed to `FacebookAdsApi.init()` for the Insights stream's SDK-based requests

### `start_date`

**Type**: datetime (ISO 8601)
**Required**: Yes (for insight streams)

The earliest date from which to sync data. Used directly by AdsInsightStream to determine the beginning of the date range. Also serves as the initial replication key value for incremental streams on their first sync.

Example: `"2023-03-01T00:00:00Z"`

Note: Facebook stores insight metrics for a maximum of 37 months. If `start_date` is older than 36 months from today, the tap automatically adjusts to the oldest allowed date.

---

## Optional Settings

### `api_version`

**Type**: string
**Default**: `"v25.0"`

The Facebook Graph API version string to use. This is interpolated into the base URL for all API requests: `https://graph.facebook.com/{api_version}/`.

### `end_date`

**Type**: datetime (ISO 8601)
**Default**: today's date

The latest date to sync data through. Only used by AdsInsightStream to cap the date range for insight queries. If not set, defaults to today.

Example: `"2023-03-31T00:00:00Z"`

### `locations`

**Type**: array of objects
**Default**: `[]`

A list of ad account location objects used to filter which ad accounts are synced. Each entry has:
- `id` (required, string): The ad account ID (with or without the `act_` prefix)
- `name` (optional, string): A display name for the location

When set, the tap will:
1. Only sync child streams for accounts matching these IDs.
2. If the `adaccounts` stream itself is not selected, yield minimal records with just `account_id` so child streams still receive context.

The tap also supports legacy formats for backward compatibility:
- A list of plain strings (treated as account IDs)
- A comma-separated string of account IDs

Example (current format):
```json
{
  "locations": [
    {"id": "123456789", "name": "Main Account"},
    {"id": "act_987654321", "name": "Secondary Account"}
  ]
}
```

### `insight_reports_list`

**Type**: array of objects
**Default**: `[]`

A list of custom insight report definitions. Each report generates a separate `adsinsights_{name}` stream. A built-in "default" report is always included in addition to any custom reports defined here.

Each report object accepts the following properties:

| Property | Type | Default | Description |
|---|---|---|---|
| `name` | string | (required) | Unique name for the report. Included in the stream name (`adsinsights_{name}`). Changing this affects bookmark keys. |
| `level` | string | `"ad"` | Aggregation level: `ad`, `adset`, `campaign`, or `account`. |
| `breakdowns` | array of strings | `[]` | Dimensions to break down results by (e.g., `["age", "gender"]`). Added to primary keys. See [Facebook Breakdowns docs](https://developers.facebook.com/docs/marketing-api/insights/breakdowns). |
| `action_breakdowns` | array of strings | `[]` | How to break down action results (e.g., `["action_type"]`). |
| `time_increment_days` | integer | `1` | Number of days per aggregation window. `1` = daily granularity. |
| `action_attribution_windows_view` | string | `"1d_view"` | View-through attribution window (e.g., `"1d_view"`, `"7d_view"`, `"28d_view"`). |
| `action_attribution_windows_click` | string | `"7d_click"` | Click-through attribution window (e.g., `"1d_click"`, `"7d_click"`, `"28d_click"`). |
| `action_report_time` | string | `"mixed"` | When to attribute actions: `"impression"`, `"conversion"`, or `"mixed"`. |
| `lookback_window` | integer | `28` | Number of days to re-fetch on incremental syncs. Facebook freezes insight data after 28 days, so this ensures recently-updated data is re-synced. |

Example:
```json
{
  "insight_reports_list": [
    {
      "name": "age_gender_daily",
      "level": "ad",
      "breakdowns": ["age", "gender"],
      "time_increment_days": 1,
      "lookback_window": 28
    },
    {
      "name": "platform_weekly",
      "level": "campaign",
      "breakdowns": ["publisher_platform"],
      "time_increment_days": 7,
      "action_attribution_windows_view": "7d_view",
      "action_attribution_windows_click": "28d_click"
    }
  ]
}
```

The built-in default report (always present) is configured as:
```json
{
  "name": "default",
  "level": "ad",
  "action_breakdowns": [],
  "breakdowns": [],
  "time_increment_days": 1,
  "action_attribution_windows_view": "1d_view",
  "action_attribution_windows_click": "7d_click",
  "action_report_time": "mixed",
  "lookback_window": 28
}
```

---

## Full Example Config

```json
{
  "access_token": "EAAxxxxxxx...",
  "api_version": "v25.0",
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-12-31T00:00:00Z",
  "locations": [
    {"id": "123456789", "name": "Dishio Main"}
  ],
  "insight_reports_list": [
    {
      "name": "age_gender",
      "level": "ad",
      "breakdowns": ["age", "gender"],
      "time_increment_days": 1,
      "lookback_window": 28
    }
  ]
}
```

## Meltano Configuration

The tap is registered in `meltano.yml` with these settings:

```yaml
plugins:
  extractors:
  - name: tap-facebook
    namespace: tap_facebook
    pip_url: -e .
    capabilities:
    - state
    - catalog
    - discover
    settings:
    - name: access_token
      kind: password
    - name: start_date
      kind: date_iso8601
    - name: end_date
      kind: date_iso8601
    - name: locations
      kind: array
    - name: api_version
```

Set config values via environment variables (`TAP_FACEBOOK_ACCESS_TOKEN`, etc.) or `meltano config tap-facebook set`.
