---
name: meltano-sdk-development
description: Use this skill when working on Meltano Singer SDK taps, modifying stream definitions, configuring meltano.yml, writing schemas, handling pagination/auth, or debugging SDK-based extractors.
---

# Meltano Singer SDK Development

## Project Structure

A Meltano SDK tap project follows this layout:

```
tap_<name>/
  __init__.py
  tap.py              # Tap class: config schema, stream discovery
  client.py           # Base stream class: auth, pagination, error handling
  streams/
    __init__.py        # Re-exports all stream classes
    base_streams.py    # Shared base classes (e.g., AccountLevelStream)
    <stream>.py        # One file per stream/endpoint
tests/
  __init__.py
  conftest.py
  test_core.py         # SDK test suite via get_tap_test_class
meltano.yml            # Meltano project config (extractors, settings, environments)
pyproject.toml         # Poetry build system with poetry-dynamic-versioning
```

## Tap Class (tap.py)

The tap class subclasses `singer_sdk.Tap` and defines:

- `name`: The tap identifier string.
- `config_jsonschema`: A JSON Schema dict built with `singer_sdk.typing` helpers. Use `th.PropertiesList(...).to_dict()` to produce the schema.
- `discover_streams()`: Returns a list of stream instances. This is where you instantiate each stream class and pass any custom constructor arguments.

```python
from singer_sdk import Tap
from singer_sdk import typing as th

class TapExample(Tap):
    name = "tap-example"
    config_jsonschema = th.PropertiesList(
        th.Property("api_key", th.StringType, required=True),
        th.Property("start_date", th.DateTimeType),
    ).to_dict()

    def discover_streams(self):
        return [MyStream(tap=self)]
```

The CLI entry point is declared in `pyproject.toml` under `[tool.poetry.scripts]`:

```toml
tap-example = 'tap_example.tap:TapExample.cli'
```

## Client / Base Stream Class (client.py)

The client module defines a base `RESTStream` subclass shared by all REST-based streams. Key attributes and methods:

### URL Construction

```python
from singer_sdk.streams import RESTStream

class MyBaseStream(RESTStream):
    @property
    def url_base(self) -> str:
        version = self.config["api_version"]
        return f"https://api.example.com/{version}"
```

### Authentication

The SDK provides built-in authenticators. Use `BearerTokenAuthenticator` for token-based APIs:

```python
from singer_sdk.authenticators import BearerTokenAuthenticator

@property
def authenticator(self) -> BearerTokenAuthenticator:
    return BearerTokenAuthenticator.create_for_stream(
        self, token=self.config["access_token"],
    )
```

Other authenticators: `APIKeyAuthenticator`, `OAuthAuthenticator`, `OAuthJWTAuthenticator`.

### Pagination

Set `next_page_token_jsonpath` to extract the cursor from the response JSON, or override `get_next_page_token()` for custom logic:

```python
records_jsonpath = "$.data[*]"
next_page_token_jsonpath = "$.paging.cursors.after"

def get_next_page_token(self, response, previous_token):
    all_matches = extract_jsonpath(self.next_page_token_jsonpath, response.json())
    return next(iter(all_matches), None)

def get_url_params(self, context, next_page_token):
    params = {"limit": 25}
    if next_page_token:
        params["after"] = next_page_token
    return params
```

Common pagination patterns:
- **Cursor-based**: Extract cursor from response body via jsonpath (Facebook Graph API pattern).
- **Offset-based**: Track page number or offset in `get_url_params`.
- **Link header**: Parse `response.headers["Link"]` or `response.headers["X-Next-Page"]`.
- **Next URL**: Return full URL from `get_next_page_token`, override `get_url` to use it.

### Error Handling

Override `validate_response()` to classify errors as fatal or retriable:

```python
from singer_sdk.exceptions import FatalAPIError, RetriableAPIError

def validate_response(self, response):
    if response.status_code == 429:
        raise RetriableAPIError("Rate limited", response)
    if 400 <= response.status_code < 500:
        raise FatalAPIError(f"Client error: {response.status_code}", response)
    if response.status_code >= 500:
        raise RetriableAPIError(f"Server error: {response.status_code}", response)
```

Control retry behavior with `backoff_max_tries()` (return int) and `backoff_wait_generator()`.

## Stream Types and Replication

### Full Table Replication

No replication key needed. The entire dataset is fetched on every sync.

```python
class MyFullTableStream(MyBaseStream):
    name = "my_stream"
    path = "/endpoint"
    primary_keys = ["id"]
    # replication_method defaults to FULL_TABLE
```

### Incremental Replication

Set `replication_key` and `replication_method = REPLICATION_INCREMENTAL`. The SDK automatically manages bookmarks:

```python
from singer_sdk.streams.core import REPLICATION_INCREMENTAL

class MyIncrementalStream(MyBaseStream):
    name = "my_stream"
    path = "/endpoint"
    primary_keys = ["id", "updated_time"]
    replication_key = "updated_time"
    replication_method = REPLICATION_INCREMENTAL
```

Use `self.get_starting_replication_key_value(context)` to retrieve the bookmark value and apply it as an API filter (query param, request body, etc.).

## Parent-Child Streams and Context Passing

Parent streams emit context dicts that child streams receive. The parent defines `get_child_context()` and children set `parent_stream_type`:

```python
# Parent
class AccountsStream(MyBaseStream):
    name = "accounts"
    def get_child_context(self, record, context):
        return {"account_id": record["account_id"]}

# Child
class AdsStream(MyBaseStream):
    name = "ads"
    parent_stream_type = AccountsStream

    @property
    def url_base(self):
        return super().url_base + "/act_{account_id}"
```

The `{account_id}` in the URL is automatically interpolated from the context dict. You can also filter child syncs by overriding `_sync_children()` on the parent.

## Schema Definition

Use `singer_sdk.typing` (imported as `th`) to build schemas declaratively:

```python
from singer_sdk.typing import (
    PropertiesList, Property,
    StringType, IntegerType, NumberType, BooleanType,
    DateTimeType, ArrayType, ObjectType,
)

schema = PropertiesList(
    Property("id", StringType, required=True),
    Property("name", StringType),
    Property("amount", NumberType),
    Property("is_active", BooleanType),
    Property("tags", ArrayType(StringType)),
    Property("metadata", ObjectType(
        Property("created_at", DateTimeType),
        Property("source", StringType),
    )),
).to_dict()
```

For dynamic schemas (e.g., when breakdowns add columns), build the `PropertiesList` in a `@property` method:

```python
@property
def schema(self) -> dict:
    props = [th.Property("id", th.StringType())]
    for breakdown in self._report_definition["breakdowns"]:
        props.append(th.Property(breakdown, th.StringType()))
    return th.PropertiesList(*props).to_dict()
```

## Non-REST Streams (Stream base class)

For APIs that don't follow standard REST patterns (e.g., the Facebook Business SDK), subclass `Stream` directly and override `get_records()`:

```python
from singer_sdk.streams.core import Stream

class CustomStream(Stream):
    name = "custom"
    def get_records(self, context):
        # Use any client library or logic here
        for record in some_sdk_call():
            yield record
```

## Post-Processing Records

Override `post_process()` to transform records after they are fetched but before they are emitted:

```python
def post_process(self, row, context=None):
    row["amount"] = int(row["amount"]) if "amount" in row else None
    return row  # Return None to skip the record
```

## Testing

The SDK provides a built-in test suite via `get_tap_test_class`:

```python
from singer_sdk.testing import SuiteConfig, get_tap_test_class
from my_tap.tap import TapExample

SAMPLE_CONFIG = {"api_key": "test", "start_date": "2024-01-01T00:00:00Z"}

TestTapExample = get_tap_test_class(
    TapExample,
    config=SAMPLE_CONFIG,
    suite_config=SuiteConfig(
        max_records_limit=20,
        ignore_no_records_for_streams=["optional_stream"],
    ),
)
```

This auto-generates tests for discovery, schema validation, record emission, and state handling. Add custom test functions in the same file for stream-specific logic.

## meltano.yml Configuration

```yaml
version: 1
default_environment: dev
project_id: tap-example
plugins:
  extractors:
  - name: tap-example
    namespace: tap_example
    pip_url: -e .          # Editable install for local dev
    capabilities:
    - state              # Supports incremental state
    - catalog            # Supports catalog selection
    - discover           # Supports schema discovery
    settings:
    - name: access_token
      kind: password
    - name: start_date
      kind: date_iso8601
    - name: locations
      kind: array
environments:
- name: dev
```

Key `capabilities`: `state`, `catalog`, `discover`, `about`, `stream-maps`, `schema-flattening`, `batch`.

## Build System

Uses Poetry with `poetry-dynamic-versioning` for git-tag-based versioning:

```toml
[build-system]
requires = ["poetry-core>=2.0,<3.0", "poetry-dynamic-versioning>=1.10,<2.0"]
build-backend = "poetry_dynamic_versioning.backend"

[tool.poetry-dynamic-versioning]
enable = true
```

Common commands:
- `poetry install` -- install dependencies
- `poetry run tap-example --config config.json --discover` -- discover schemas
- `poetry run tap-example --config config.json` -- run sync
- `poetry run pytest` -- run tests
- `poetry run ruff check .` -- lint

## Common Patterns in This Codebase

- **Location filtering**: The `AdAccountsStream` supports a `locations` config to filter which ad accounts are synced. Child streams inherit this filter via context.
- **Incremental filtering via API params**: `IncrementalFacebookStream` converts the bookmark to a Unix timestamp and passes it as a `filtering` JSON parameter.
- **Columns list pattern**: Streams define a `columns` list that gets passed as the `fields` query parameter to the Facebook Graph API.
- **Tolerated HTTP errors**: Set `tolerated_http_errors` on a stream to log-and-skip certain status codes instead of raising.
- **Insight reports**: `AdsInsightStream` uses `facebook-business` SDK directly (not RESTStream), with batch API calls and custom rate limit handling.
