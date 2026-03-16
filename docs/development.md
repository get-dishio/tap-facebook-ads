# Development Guide

## Prerequisites

- Python >= 3.10
- [Poetry](https://python-poetry.org/) for dependency management
- A Facebook Marketing API access token with `ads_read` permission
- An ad account ID to test against

## Setup

1. Clone the repository and install dependencies:

```bash
cd tap-facebook-ads
poetry install
```

2. Set required environment variables for testing:

```bash
export TAP_FACEBOOK_ACCESS_TOKEN="EAAxxxxxxx..."
export TAP_FACEBOOK_ACCOUNT_ID="123456789"
```

3. Verify the installation:

```bash
poetry run tap-facebook --help
```

## CLI Entry Points

The project registers multiple CLI aliases in `pyproject.toml`, all pointing to the same `TapFacebook.cli` entry point:

- `tap-facebook`
- `tap-facebook-ads`
- `tap-facebook-v2`
- `tap-facebook-ads-v2`

## Running the Tap

### Discover mode (output the catalog):

```bash
poetry run tap-facebook --config config.json --discover
```

### Sync mode:

```bash
poetry run tap-facebook --config config.json
```

### With Meltano:

```bash
meltano run tap-facebook target-jsonl
```

### With state (incremental):

```bash
poetry run tap-facebook --config config.json --state state.json
```

## Running Tests

Tests use the Singer SDK's built-in test suite plus custom unit tests. They require live API access (no mocking).

```bash
poetry run pytest
```

The test suite (`tests/test_core.py`) uses `get_tap_test_class` from `singer_sdk.testing` which runs standard Singer tap compliance tests:
- Schema validation
- Record output verification
- State handling

Test configuration:
- `max_records_limit`: 20 (caps records per stream to keep tests fast)
- `ignore_no_records_for_streams`: `["adlabels", "customconversions"]` (these may be empty in test accounts)

There is also a unit test for `AdAccountsStream.post_process()` that verifies string-to-integer casting of budget fields.

## Linting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
poetry run ruff check .
poetry run ruff format .
```

Configuration is in `pyproject.toml`:
- Line length: 100
- Target: Python 3.10
- All rules enabled (`select = ["ALL"]`) with specific ignores for `ANN101`, `DJ`, `PD`, `D101`, `D102`
- `typing` module must be imported as `t` (enforced by `flake8-import-conventions`)

## Adding a New REST Stream

1. Create a new file in `tap_facebook/streams/` (e.g., `my_new_stream.py`).

2. Choose the appropriate base class:
   - `AccountLevelStream` -- for streams under `/act_{account_id}/` with no server-side incremental filtering
   - `IncrementalFacebookStream` -- for streams that support server-side filtering via the Facebook `filtering` parameter (requires a `filter_entity` attribute)

3. Define the stream class:

```python
from singer_sdk.streams.core import REPLICATION_INCREMENTAL
from singer_sdk.typing import PropertiesList, Property, StringType
from tap_facebook.streams.base_streams import AccountLevelStream

class MyNewStream(AccountLevelStream):
    columns = ["id", "name", "created_time"]
    name = "my_new_stream"
    path = f"/my_endpoint?fields={columns}"
    primary_keys = ["id"]
    replication_method = REPLICATION_INCREMENTAL
    replication_key = "created_time"

    schema = PropertiesList(
        Property("id", StringType),
        Property("name", StringType),
        Property("created_time", StringType),
    ).to_dict()
```

4. Register it in `tap_facebook/streams/__init__.py`:

```python
from tap_facebook.streams.my_new_stream import MyNewStream
```

5. Add it to the `STREAM_TYPES` list in `tap_facebook/tap.py`:

```python
STREAM_TYPES = [
    # ... existing streams ...
    MyNewStream,
]
```

### Key patterns to follow

- **columns**: A list of field names passed as the `fields` query parameter to the Graph API. This tells Facebook which fields to return.
- **columns_remaining**: (Optional) Fields that exist but are not yet requested. Useful for tracking what could be added later.
- **path**: The URL path appended to the base URL. For `AccountLevelStream` subclasses, the base URL already includes `/act_{account_id}`, so paths like `/ads?fields=...` work directly.
- **filter_entity**: Required for `IncrementalFacebookStream`. The entity name used in the `filtering` parameter (e.g., `"ad"`, `"adset"`, `"campaign"`).
- **post_process()**: Override to transform records after extraction (e.g., type casting, field renaming).

## Debugging

### Rate Limit Issues

**REST streams**: Look for log messages containing "too many calls" or "request limit reached". The tap retries these automatically up to 20 times with exponential backoff.

**Insights stream**: Look for log messages about "Rate Limit Reached" and "Cooling Time 5 Minutes". The proactive threshold is 75% of the rate limit. If you consistently hit this, consider:
- Reducing `BATCH_SIZE` (currently 30)
- Increasing `USAGE_LIMIT_THRESHOLD` to delay the cooldown (not recommended for production)
- Reducing the number of concurrent insight reports

### Empty Insight Data

If insights return no data for a date range, the tap uses `_get_earliest_record_date()` to find the actual first date with data. Check logs for "No data found for the specified date range" or "Adjusting report start from ... to earliest available date ...".

### 37-Month Limit

Facebook only stores insight metrics for 37 months. If your `start_date` is older, the tap adjusts automatically and logs: "Report start date '...' is older than 37 months. Using oldest allowed start date '...' instead."

### Batch API Failures

Individual batch items that fail are retried separately. Look for log messages like:
- "Batch request for date ... failed due to rate limiting. Retrying individual request."
- "500 Server Error on individual request. Retrying in ... seconds."

If all 5 retries fail, the tap raises a `RuntimeError` with "Max retries exceeded for individual request".

### Common Environment Variables

| Variable | Purpose |
|---|---|
| `TAP_FACEBOOK_ACCESS_TOKEN` | API token (used in tests and Meltano) |
| `TAP_FACEBOOK_ACCOUNT_ID` | Ad account ID (used in tests) |

## Versioning

The project uses [poetry-dynamic-versioning](https://github.com/mtkennerly/poetry-dynamic-versioning) which derives the version from git tags. The version in `pyproject.toml` is set to `0.0.0` as a placeholder.
