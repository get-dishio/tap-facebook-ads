---
name: singer-tap-protocol
description: Use this skill when working with the Singer specification, tap lifecycle, state/bookmark management, catalog selection, message formats, rate limiting, or common tap patterns like date windowing and cursor pagination.
---

# Singer Protocol and Tap Patterns

## Singer Specification Overview

Singer is a specification for moving data between systems. A **tap** extracts data and writes Singer messages to stdout. A **target** reads those messages from stdin and loads data into a destination.

All communication happens via newline-delimited JSON messages on stdout. Three message types:

### RECORD Message

```json
{"type": "RECORD", "stream": "ads", "record": {"id": "123", "name": "My Ad"}, "time_extracted": "2024-01-15T10:30:00Z"}
```

### SCHEMA Message

Emitted before records for a stream. Declares the JSON Schema and key properties:

```json
{"type": "SCHEMA", "stream": "ads", "schema": {"properties": {"id": {"type": "string"}, "name": {"type": "string"}}}, "key_properties": ["id"], "bookmark_properties": ["updated_time"]}
```

### STATE Message

Emitted periodically to checkpoint progress. The target writes the state to a file so the tap can resume:

```json
{"type": "STATE", "value": {"bookmarks": {"ads": {"replication_key_value": "2024-01-15T10:00:00Z"}}}}
```

## Tap Lifecycle

1. **Discovery** (`--discover`): The tap introspects the API and outputs a catalog JSON describing all available streams, their schemas, metadata, and replication methods.

2. **Catalog Selection**: The user (or orchestrator) selects which streams and properties to sync by setting `"selected": true` in the catalog metadata.

3. **Sync** (default mode): The tap reads config, optional state (bookmarks), and the selected catalog. It then:
   - Emits SCHEMA messages for each selected stream.
   - Fetches data from the API, emitting RECORD messages.
   - Periodically emits STATE messages to checkpoint progress.

```bash
# Discovery
tap-facebook --config config.json --discover > catalog.json

# Sync (first run, no state)
tap-facebook --config config.json --catalog catalog.json

# Sync (incremental, with state from previous run)
tap-facebook --config config.json --catalog catalog.json --state state.json
```

## State Management and Bookmarking

State tracks sync progress per stream. For incremental streams, the bookmark is typically the highest value of the replication key seen so far.

### State Structure

```json
{
  "bookmarks": {
    "ads": {
      "replication_key": "updated_time",
      "replication_key_value": "2024-01-15T10:00:00Z"
    },
    "campaigns": {
      "replication_key": "updated_time",
      "replication_key_value": "2024-01-14T08:00:00Z"
    }
  }
}
```

### State with Parent-Child Streams (Partitioned State)

When a stream has a parent (e.g., ads under ad accounts), state is partitioned by context:

```json
{
  "bookmarks": {
    "ads": {
      "partitions": [
        {
          "context": {"account_id": "12345"},
          "replication_key": "updated_time",
          "replication_key_value": "2024-01-15T10:00:00Z"
        },
        {
          "context": {"account_id": "67890"},
          "replication_key": "updated_time",
          "replication_key_value": "2024-01-12T06:00:00Z"
        }
      ]
    }
  }
}
```

### Bookmark Best Practices

- Always emit state after completing a stream or a logical checkpoint (e.g., after processing a full page or date window).
- For date-based incremental streams, consider a **lookback window** to re-fetch recent data that may have been updated after initial extraction. Facebook Ads Insights uses a 28-day lookback because metrics can change retroactively.
- Never advance the bookmark past data you have not yet successfully emitted.
- With the Meltano SDK, bookmark management is automatic when you set `replication_key` and `replication_method`.

## Config Validation

Tap config is validated against the `config_jsonschema` defined on the Tap class. The Meltano SDK validates automatically at startup. Common pattern:

```python
config_jsonschema = th.PropertiesList(
    th.Property("access_token", th.StringType, required=True),
    th.Property("start_date", th.DateTimeType, required=True),
    th.Property("end_date", th.DateTimeType),
    th.Property("api_version", th.StringType, default="v25.0"),
).to_dict()
```

Required properties cause the tap to fail fast if missing. Default values are applied automatically.

## Stream Maps and Schema Flattening

The Singer SDK supports **stream maps** for inline transformations and **schema flattening** for denormalizing nested objects. These are configured in `meltano.yml` or `config.json`:

```yaml
# Stream maps: rename, filter, hash, or transform fields
stream_maps:
  ads:
    name: ad_name       # Rename 'name' -> 'ad_name'
    __filter__: record["status"] == "ACTIVE"  # Filter records

# Schema flattening: flatten nested objects to top-level columns
flattening_enabled: true
flattening_max_depth: 1  # ads.creative.id -> ads__creative__id
```

## Handling API Rate Limits and Backoff

### Singer SDK Built-in Backoff

The SDK uses the `backoff` library. Override these on your stream class:

- `backoff_max_tries()` -- Maximum retry attempts (default 5). Return `None` for infinite retries.
- `backoff_wait_generator()` -- Generator yielding wait times. Default is exponential backoff.
- `backoff_handler()` -- Called on each retry; useful for logging.

### Custom Rate Limit Handling

For APIs with explicit rate limit headers (e.g., Facebook `x-business-use-case-usage`):

```python
def check_limit(self, account_id):
    usage = self.get_current_usage(account_id)
    if usage > 75:  # 75% threshold
        self.logger.warning("Rate limit threshold reached. Cooling for 5 minutes.")
        time.sleep(300)
```

### Retriable vs Fatal Errors

- **RetriableAPIError**: The SDK retries automatically with backoff. Use for 429, 500, 502, 503, 504, and rate-limit responses embedded in 400 responses.
- **FatalAPIError**: The SDK stops immediately. Use for 401 (auth failure), 403 (forbidden), 404 (not found), and other non-transient errors.

## Common Tap Patterns

### Date Windowing

Break large date ranges into smaller windows to avoid API timeouts and memory issues:

```python
def get_records(self, context):
    start = self._get_start_date(context)
    end = pendulum.today().date()
    while start < end:
        window_end = min(start.add(days=self.window_size), end)
        params = {"since": start.format("YYYY-MM-DD"), "until": window_end.format("YYYY-MM-DD")}
        yield from self._fetch_window(params)
        start = window_end
```

This is the pattern used by `AdsInsightStream` in this codebase, which processes data in batches of 30 days using the Facebook Batch API.

### Cursor Pagination

Most common for REST APIs. Extract cursor from response, pass it back on next request:

```python
records_jsonpath = "$.data[*]"
next_page_token_jsonpath = "$.paging.cursors.after"

def get_url_params(self, context, next_page_token):
    params = {"limit": 25}
    if next_page_token:
        params["after"] = next_page_token
    return params
```

### Offset Pagination

```python
def get_url_params(self, context, next_page_token):
    params = {"limit": 100, "offset": next_page_token or 0}
    return params

def get_next_page_token(self, response, previous_token):
    data = response.json()
    offset = (previous_token or 0) + len(data["results"])
    return offset if offset < data["total"] else None
```

### Parent-Child Streams

Parent stream emits context; child stream consumes it. The child automatically syncs once per parent record:

```python
# Parent emits context
def get_child_context(self, record, context):
    return {"account_id": record["account_id"]}

# Child uses context in URL
class ChildStream(BaseStream):
    parent_stream_type = ParentStream
    path = "/accounts/{account_id}/items"
```

### Filtering Parent-Child Syncs

Override `_sync_children()` on the parent to skip child syncs for certain contexts:

```python
def _sync_children(self, child_context):
    if child_context["account_id"] not in self.allowed_accounts:
        return
    super()._sync_children(child_context)
```

### Batch API Requests

For APIs that support batch endpoints (like Facebook), send multiple requests in a single HTTP call:

```python
batch_requests = [
    {"method": "GET", "relative_url": f"act_{id}/insights?{urlencode(params)}"}
    for id, params in request_params
]
response = api.call("POST", ["/"], params={"batch": json.dumps(batch_requests)})
for item in response.json():
    if item["code"] == 200:
        yield from json.loads(item["body"])["data"]
```

### Handling API Fields Selection

Many APIs accept a `fields` parameter to select which columns to return. Define a `columns` list per stream and pass it as a query parameter:

```python
columns = ["id", "name", "status", "updated_time"]
path = f"/endpoint?fields={columns}"
# or
def get_url_params(self, context, next_page_token):
    params = super().get_url_params(context, next_page_token)
    params["fields"] = ",".join(self.columns)
    return params
```

### Dynamic Schemas from SDK Metadata

When the schema depends on API metadata (like the Facebook Business SDK's `_field_types`), build it dynamically:

```python
@property
def schema(self) -> dict:
    properties = []
    for field in self.selected_columns:
        dtype = self._resolve_type(field)
        properties.append(th.Property(field, dtype))
    return th.PropertiesList(*properties).to_dict()
```

## Debugging Tips

- Run with `--discover` first to validate schemas.
- Use `SINGER_SDK_LOG_CONFIG` or `LOGLEVEL=DEBUG` to see detailed request/response logs.
- Pipe output to a file to inspect raw Singer messages: `tap-example --config config.json > output.jsonl`.
- Test individual streams using the SDK test suite with `max_records_limit` to avoid long syncs.
- Check state output for correct bookmark advancement after each run.
