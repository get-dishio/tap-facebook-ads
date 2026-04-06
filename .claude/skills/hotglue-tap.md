---
name: hotglue-tap-development
description: Use this skill when developing, deploying, or debugging Singer taps for HotGlue, including config injection, state handling, container packaging, output format, credential management, and local testing before HotGlue deployment.
---

# HotGlue Tap Development and Deployment

## HotGlue Connector Architecture

HotGlue is an embedded ETL platform that runs Singer taps as containerized connectors. Each tap runs in an isolated container (Docker) managed by HotGlue's infrastructure. The flow is:

1. User configures the connector through HotGlue's UI or API.
2. HotGlue injects the configuration as `config.json` into the container.
3. The tap runs, emitting Singer messages (SCHEMA, RECORD, STATE) to stdout.
4. HotGlue captures the output, routes records to the configured target, and persists state.
5. On the next run, HotGlue injects the saved state as `state.json` so the tap resumes incrementally.

```
HotGlue UI/API
    |
    v
config.json ------+
state.json -------+----> [Docker Container: tap-facebook] ----> stdout (Singer messages)
catalog.json -----+                                                |
                                                                   v
                                                         HotGlue captures output
                                                         -> routes to target
                                                         -> saves state.json
```

## Config Injection

HotGlue maps UI fields to a `config.json` that is mounted into the container at runtime. The config keys must match what the tap expects in its `config_jsonschema`.

For this tap (`tap-facebook-ads`), the HotGlue-injected config typically contains:

```json
{
  "access_token": "<facebook-access-token>",
  "api_version": "v25.0",
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-12-31T00:00:00Z",
  "locations": [
    {"id": "123456789", "name": "My Location"}
  ],
  "insight_reports_list": []
}
```

Key considerations:
- **Sensitive values** (like `access_token`) are stored encrypted by HotGlue and injected at runtime. Never hardcode credentials.
- **Location filtering**: The `locations` array controls which ad accounts are synced. HotGlue's UI lets users select locations, which map to `{"id": "<account_id>", "name": "<display_name>"}` objects.
- **Date ranges**: `start_date` and `end_date` may be set by HotGlue based on the user's sync schedule or manual configuration.
- **Default values**: Ensure your tap's `config_jsonschema` has sensible defaults for optional fields, since HotGlue may not always pass every setting.

## State Management

HotGlue handles state persistence between runs automatically:

- After each successful run, HotGlue saves the final STATE message emitted by the tap.
- On the next run, the saved state is passed as `state.json` to the container.
- The Meltano SDK automatically reads `state.json` and uses bookmark values to resume incremental syncs.

### State Gotchas in HotGlue

- **First run**: No `state.json` exists. The tap should fall back to `start_date` from config.
- **Failed runs**: If the tap crashes mid-sync, HotGlue may not have received a STATE message. The next run restarts from the last successfully saved state.
- **State reset**: Users can reset state through the HotGlue UI, which removes `state.json` and forces a full re-sync from `start_date`.
- **Partitioned state**: For parent-child streams (like ad accounts -> ads), state is partitioned by parent context. If new ad accounts are added to `locations`, they start syncing from `start_date` while existing accounts resume from their bookmark.

## Output Format Expectations

HotGlue expects standard Singer protocol output on stdout:

1. **SCHEMA** messages before any records for a stream.
2. **RECORD** messages with the actual data.
3. **STATE** messages to checkpoint progress.

All logging must go to **stderr**, not stdout. The Meltano SDK handles this correctly by default (`self.logger` writes to stderr). Never use `print()` for debugging; it goes to stdout and corrupts the Singer message stream.

```python
# Correct: logs to stderr
self.logger.info("Processing account %s", account_id)

# Wrong: goes to stdout, breaks Singer output
print(f"Processing account {account_id}")
```

## Debugging HotGlue Connector Issues

### Common Issues

1. **Auth failures**: The access token expired or was revoked. HotGlue stores tokens and may need a re-auth flow. Check for 401/403 responses in logs.

2. **Rate limiting**: Facebook's Marketing API has aggressive rate limits. The tap handles this with backoff, but long-running syncs across many accounts can still hit limits. Look for "Rate Limit Reached" or "too many calls" in logs.

3. **Missing data**: If a stream returns no records:
   - Check if `locations` config is filtering out the expected accounts.
   - Verify `start_date` and `end_date` bracket the expected data range.
   - For insights, Facebook stores data for a maximum of 37 months. Dates older than that return empty results.

4. **Schema mismatches**: If the API returns fields not in the schema, they are silently dropped. If required fields are missing, the tap may error. Check the stream's `schema` definition.

5. **Container timeouts**: HotGlue has execution time limits. Large syncs may need to be broken into smaller date ranges or fewer accounts.

6. **State corruption**: If a run partially completes but state is saved, you may see duplicate or missing records. The lookback window (28 days for insights) mitigates this.

### Debugging Steps

1. **Check HotGlue logs**: HotGlue captures stderr output from the container. Look for error messages, stack traces, and rate limit warnings.

2. **Reproduce locally**: Run the tap locally with the same `config.json` and `state.json` to reproduce the issue (see "Testing Locally" below).

3. **Inspect state**: Check what bookmark values HotGlue has stored. A stuck or future-dated bookmark can cause the tap to skip data.

4. **Test with --discover**: Run discovery to verify the tap can authenticate and enumerate streams.

5. **Check API version**: Ensure `api_version` in config matches what the Facebook API currently supports. Deprecated API versions return errors.

## Version Pinning and Dependency Management

HotGlue deploys taps from specific versions. Dependency management matters for stability:

### pyproject.toml Pinning Strategy

```toml
[tool.poetry.dependencies]
python = ">=3.10"
singer-sdk = ">=0.53,<0.54"       # Pin to minor version for SDK stability
facebook-business = "^25.0.0"      # Allow patch updates within major version
requests = "~=2.32.0"              # Pin to patch level for HTTP stability
```

### Best Practices

- **Pin `singer-sdk` tightly**: The SDK can introduce breaking changes between minor versions. Pin to a specific minor range (e.g., `>=0.53,<0.54`).
- **Pin `facebook-business` to major**: Facebook's SDK follows semver. Major bumps may change API behavior or remove fields.
- **Lock file**: Always commit `poetry.lock` so HotGlue builds reproduce exactly.
- **Test before bumping**: When upgrading dependencies, run the full test suite and a local sync before deploying to HotGlue.
- **Container base image**: HotGlue uses specific Python base images. Ensure your `python` version constraint matches what HotGlue supports (currently `>=3.10`).

### Versioning the Tap

The tap uses `poetry-dynamic-versioning` to derive versions from git tags:

```toml
[tool.poetry-dynamic-versioning]
enable = true
```

Tag releases with semver (e.g., `v1.2.3`) and the version is automatically set during build.

## Testing Locally Before HotGlue Deployment

### Basic Local Test

```bash
# Install the tap
poetry install

# Create a config.json matching what HotGlue would inject
cat > config.json <<EOF
{
  "access_token": "<your-token>",
  "api_version": "v25.0",
  "start_date": "2024-01-01T00:00:00Z",
  "locations": [{"id": "<your-account-id>"}]
}
EOF

# Run discovery
poetry run tap-facebook --config config.json --discover > catalog.json

# Run a sync (first run, no state)
poetry run tap-facebook --config config.json > output.jsonl

# Run with state (simulating HotGlue's incremental behavior)
poetry run tap-facebook --config config.json --state state.json > output.jsonl
```

### Using Meltano Locally

```bash
# Install meltano
pip install meltano

# Initialize (if not already done)
meltano install

# Run with Meltano (uses meltano.yml config)
meltano invoke tap-facebook --discover
meltano run tap-facebook target-jsonl
```

### SDK Test Suite

```bash
# Set required environment variables
export TAP_FACEBOOK_ACCESS_TOKEN="<your-token>"
export TAP_FACEBOOK_ACCOUNT_ID="<your-account-id>"

# Run tests
poetry run pytest

# Run with verbose output
poetry run pytest -v -s
```

### Simulating HotGlue's Runtime

To closely replicate HotGlue's environment:

1. Build the Docker image if a Dockerfile exists.
2. Mount `config.json`, `state.json`, and `catalog.json` into the container.
3. Run the tap and capture stdout/stderr separately.

```bash
docker build -t tap-facebook .
docker run --rm \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/state.json:/app/state.json \
  tap-facebook --config /app/config.json --state /app/state.json \
  > output.jsonl 2> error.log
```

## Common HotGlue-Specific Patterns

### Location Filtering

HotGlue passes a `locations` array to filter which ad accounts are synced. This is a HotGlue-specific pattern for multi-tenant setups where each Dishio customer connects their own Facebook ad accounts.

The tap's `AdAccountsStream` processes this config:

```python
@property
def configured_location_ids(self) -> list[str]:
    location_ids = []
    locations_config = self.config.get("locations")
    if locations_config:
        for entry in locations_config:
            if isinstance(entry, dict) and "id" in entry:
                location_ids.append(entry["id"])
    return [id.replace("act_", "") for id in location_ids]
```

If `locations` is empty or not provided, the tap fetches all ad accounts accessible by the token.

### Credential Handling

- **Access tokens**: Facebook access tokens expire. HotGlue handles token refresh through its OAuth integration. The tap receives a valid token in `config.json` at each run.
- **Never log tokens**: The `access_token` config setting has `kind: password` in `meltano.yml`, which tells the SDK to mask it in logs.
- **Token scopes**: The token must have `ads_read` and `ads_management` permissions for the Facebook Marketing API. Missing scopes result in 403 errors or empty results.

### Insight Report Definitions

HotGlue can pass custom insight report configurations via the `insight_reports_list` config:

```json
{
  "insight_reports_list": [
    {
      "name": "age_gender",
      "level": "ad",
      "breakdowns": ["age", "gender"],
      "action_breakdowns": [],
      "time_increment_days": 1,
      "action_attribution_windows_view": "1d_view",
      "action_attribution_windows_click": "7d_click",
      "action_report_time": "mixed",
      "lookback_window": 28
    }
  ]
}
```

The tap always creates a "default" insight report (no breakdowns), plus one additional stream per entry in `insight_reports_list`. Each becomes a separate Singer stream named `adsinsights_<name>`.

### Error Recovery

HotGlue automatically retries failed connector runs. The tap should be designed to be **idempotent** and **resumable**:

- Incremental streams resume from the last bookmark via `state.json`.
- The lookback window re-fetches recently changed data to handle retroactive updates.
- Batch API failures are retried individually with exponential backoff (see `_execute_single_request_with_retries`).
- Rate limit checks (`check_limit`) proactively back off before hitting hard limits.

### Monitoring and Alerts

HotGlue provides monitoring for connector runs. Key things to surface in logs:

- Record counts per stream/date window (the tap already logs these).
- Rate limit warnings and cooldown periods.
- Skipped accounts or date ranges due to errors.
- Total sync duration and date range covered.
