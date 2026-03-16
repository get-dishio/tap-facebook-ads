---
name: etl-reliability
description: ETL pipeline reliability patterns, error handling, rate limiting, state management, and data quality best practices for Singer/Meltano taps
---

# ETL Pipeline Reliability Reference

Comprehensive reference for building and evaluating production-grade Singer/Meltano taps. This skill covers reliability patterns, failure modes, and operational best practices.

---

## Singer Tap Reliability Checklist

### Error Handling (8 items)

- [ ] **EH-1.** All HTTP requests use explicit timeouts (connect and read).
- [ ] **EH-2.** Retriable HTTP errors (429, 500, 502, 503, 504) are retried with exponential backoff and jitter.
- [ ] **EH-3.** Fatal HTTP errors (400, 401, 403) fail immediately with clear error messages.
- [ ] **EH-4.** 404 errors are handled per-stream (skip record or stream, do not crash the entire tap).
- [ ] **EH-5.** Connection errors (`ConnectionError`, `Timeout`, `ChunkedEncodingError`) are retried.
- [ ] **EH-6.** Maximum retry count is configurable or set to a reasonable default (3-5).
- [ ] **EH-7.** Per-stream error isolation: failure in one stream does not prevent other streams from syncing.
- [ ] **EH-8.** All exceptions during sync are caught at the top level, logged with context, and re-raised with a clear message.

### Rate Limiting (5 items)

- [ ] **RL-1.** 429 responses are handled with backoff (minimum baseline).
- [ ] **RL-2.** `Retry-After` header is honored when present.
- [ ] **RL-3.** API-specific rate limit headers are read proactively (e.g., `X-RateLimit-Remaining`, `x-business-use-case-usage`).
- [ ] **RL-4.** Throttling begins BEFORE the rate limit is hit (e.g., at 75% usage).
- [ ] **RL-5.** Rate limit scope is understood (per-app, per-account, per-endpoint) and handled accordingly.

### Data Quality (7 items)

- [ ] **DQ-1.** SCHEMA messages are emitted before RECORD messages for every stream.
- [ ] **DQ-2.** All fields in emitted records are declared in the schema.
- [ ] **DQ-3.** `key_properties` are set correctly for every stream to enable downstream deduplication.
- [ ] **DQ-4.** Null values are handled according to schema nullability declarations.
- [ ] **DQ-5.** Pagination loops have termination conditions that prevent infinite loops.
- [ ] **DQ-6.** Empty API responses (200 with no data) are detected and handled (not silently swallowed).
- [ ] **DQ-7.** Date-windowed syncs produce contiguous windows with no gaps or overlaps.

### State Management (6 items)

- [ ] **SM-1.** Bookmarks are written AFTER successful record processing, never before.
- [ ] **SM-2.** Lookback window is supported for APIs with late-arriving data.
- [ ] **SM-3.** The tap handles receiving malformed or outdated state gracefully (does not crash).
- [ ] **SM-4.** State is emitted periodically during long-running syncs, not only at the end.
- [ ] **SM-5.** Parent-child stream dependencies are managed (child stream bookmarks are independent).
- [ ] **SM-6.** Interrupted syncs can resume from the last emitted state without data loss.

### Operational (7 items)

- [ ] **OP-1.** Configuration is validated at startup before any API calls.
- [ ] **OP-2.** Structured logging is used (not print statements).
- [ ] **OP-3.** Log volume does not scale linearly with record count at INFO level.
- [ ] **OP-4.** Credentials (tokens, keys, secrets) are never logged, even at DEBUG level.
- [ ] **OP-5.** Records are streamed, not buffered entirely in memory.
- [ ] **OP-6.** HTTP sessions are reused (connection pooling via `requests.Session` or equivalent).
- [ ] **OP-7.** The tap handles SIGTERM/SIGINT gracefully (emit state and exit cleanly).

### Testing (5 items)

- [ ] **TE-1.** Unit tests exist for core logic (bookmark handling, pagination, schema generation).
- [ ] **TE-2.** Integration tests exercise the full sync flow with mocked HTTP.
- [ ] **TE-3.** Error scenarios are tested (429, 500, malformed responses, empty responses).
- [ ] **TE-4.** Edge cases are tested (empty accounts, expired tokens, very large responses).
- [ ] **TE-5.** Tests are runnable without API credentials (mocked or fixtures).

---

## Common Failure Modes and Mitigations

### 1. Silent Data Loss

**Symptom:** Sync completes successfully but records are missing.

**Common causes:**
- Pagination terminates early (off-by-one, short page interpreted as last page)
- API returns 200 with empty data array due to permissions issue
- Bookmark advanced past records that were not yet available (late-arriving data)
- Date range gaps between sync windows

**Mitigations:**
- Log record counts per stream at INFO level
- Verify pagination by checking for explicit "no more pages" signals rather than inferring from page size
- Implement lookback windows for APIs with delayed data
- Validate date window contiguity

### 2. Hung Sync

**Symptom:** Sync process appears alive but makes no progress.

**Common causes:**
- No HTTP timeout set; server holds connection open indefinitely
- Infinite pagination loop (cursor cycles back to start)
- Waiting on an async job that will never complete
- Deadlock in connection pool

**Mitigations:**
- Set explicit connect and read timeouts on every HTTP call
- Implement a maximum page count safety limit
- Set timeouts on async job polling with exponential backoff
- Use connection pool with max size and timeout

### 3. Rate Limit Cascade

**Symptom:** Sync gets progressively slower and eventually fails with rate limit errors.

**Common causes:**
- No proactive throttling; tap runs at full speed until rate limited
- Retry logic retries rate limit errors without sufficient backoff
- Multiple streams consume shared rate limit budget
- Rate limit scope mismatch (tap throttles per-endpoint but limit is per-account)

**Mitigations:**
- Read rate limit headers proactively and throttle before hitting the limit
- Use exponential backoff with jitter on 429 responses
- Implement a shared rate limiter across streams when they share a budget
- Understand and respect the rate limit scope for the specific API

### 4. State Corruption

**Symptom:** Sync crashes on startup or re-syncs all data from the beginning.

**Common causes:**
- Bookmark set to a value the tap cannot parse on restart
- State references a stream that was renamed or removed
- Bookmark set before processing; crash causes bookmark to advance past unprocessed data
- State file truncated due to crash during write

**Mitigations:**
- Validate state at startup; fall back to full sync on corruption with a warning
- Handle unknown stream names in state gracefully
- Only advance bookmarks after successful record emission
- Use atomic state writes (write to temp file, then rename)

### 5. Memory Exhaustion

**Symptom:** Process killed by OOM or system becomes unresponsive.

**Common causes:**
- Loading entire API response into memory (`response.json()` on large responses)
- Accumulating all records in a list before emitting
- Large schema objects held in memory for all streams simultaneously
- Uncontrolled batch sizes

**Mitigations:**
- Stream records: emit each record as it is parsed, do not accumulate
- Use streaming JSON parsing for large responses
- Limit in-flight data to one page of records at a time
- Set maximum batch/page sizes

### 6. Credential Expiry Mid-Sync

**Symptom:** Sync starts successfully but fails hours later with 401 errors.

**Common causes:**
- OAuth access token expires during a long-running sync
- Token refresh logic only runs at startup
- Refresh token is also expired

**Mitigations:**
- Implement proactive token refresh (check expiry before each request)
- Handle 401 mid-sync by refreshing the token and retrying
- Log a clear error when the refresh token itself is expired

### 7. Schema Drift

**Symptom:** Downstream loaders fail because records contain fields not in the schema, or field types have changed.

**Common causes:**
- API adds new fields that the tap did not anticipate
- API changes field types (string to integer, or vice versa)
- Different records for the same stream have different field sets

**Mitigations:**
- Run discovery before each sync to detect schema changes
- Use `additionalProperties: true` in schemas for APIs known to add fields
- Log warnings when records contain undeclared fields
- Handle type mismatches gracefully (coerce or null out with warning)

### 8. Partial Sync Unrecoverable

**Symptom:** After a crash, the tap must re-sync everything from the beginning, wasting hours/days.

**Common causes:**
- State only emitted at the end of the sync
- Bookmark set per-sync rather than per-batch
- No intermediate state checkpointing

**Mitigations:**
- Emit state after each batch/page of records
- For date-windowed syncs, emit state after each window completes
- Test the resume-from-state flow explicitly

---

## Rate Limiting Patterns

### Pattern 1: Reactive (Minimum Baseline)

Handle 429 responses with exponential backoff.

```python
import time
import requests
from requests.exceptions import HTTPError

def request_with_retry(session, url, params, max_retries=5):
    for attempt in range(max_retries + 1):
        response = session.get(url, params=params, timeout=(10, 30))
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
            logger.warning(f"Rate limited. Retrying after {retry_after}s (attempt {attempt + 1})")
            time.sleep(retry_after)
            continue
        response.raise_for_status()
        return response
    raise Exception(f"Max retries exceeded for {url}")
```

### Pattern 2: Proactive (Header-Based)

Read rate limit headers and throttle before hitting the limit.

```python
def throttle_from_headers(response):
    remaining = int(response.headers.get("X-RateLimit-Remaining", 100))
    reset_ts = int(response.headers.get("X-RateLimit-Reset", 0))

    if remaining < 10:
        now = time.time()
        sleep_seconds = max(0, reset_ts - now)
        if sleep_seconds > 0:
            logger.info(f"Approaching rate limit ({remaining} remaining). Sleeping {sleep_seconds:.1f}s")
            time.sleep(sleep_seconds)
```

### Pattern 3: Adaptive (Percentage-Based)

For APIs like Facebook that expose usage as a percentage.

```python
def throttle_facebook(response):
    """Adaptive throttling based on Facebook x-business-use-case-usage headers."""
    usage_header = response.headers.get("x-business-use-case-usage")
    if not usage_header:
        return

    import json
    usage_data = json.loads(usage_header)
    for account_id, usage_list in usage_data.items():
        for usage in usage_list:
            call_count = usage.get("call_count", 0)
            total_cputime = usage.get("total_cputime", 0)
            total_time = usage.get("total_time", 0)
            estimated_time_to_regain = usage.get("estimated_time_to_regain_access", 0)

            max_usage = max(call_count, total_cputime, total_time)

            if max_usage >= 90:
                sleep_time = max(estimated_time_to_regain * 60, 300)
                logger.warning(f"Facebook API usage at {max_usage}%. Sleeping {sleep_time}s")
                time.sleep(sleep_time)
            elif max_usage >= 75:
                sleep_time = (max_usage / 100) * 60
                logger.info(f"Facebook API usage at {max_usage}%. Throttling: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
```

### Pattern 4: Shared Rate Limiter

When multiple streams share a rate limit budget.

```python
import threading
import time

class SharedRateLimiter:
    """Thread-safe rate limiter shared across streams."""

    def __init__(self, max_calls_per_second=10):
        self._lock = threading.Lock()
        self._min_interval = 1.0 / max_calls_per_second
        self._last_call = 0.0

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()
```

---

## State Management Anti-Patterns

### Anti-Pattern 1: Optimistic Bookmark

```python
# WRONG: Bookmark set before processing
state["bookmarks"][stream_name] = {"updated_at": end_date}
singer.write_state(state)
for record in fetch_records(start_date, end_date):
    singer.write_record(stream_name, record)  # If this crashes, data is lost
```

**Fix:** Set bookmark after processing.

```python
# CORRECT: Bookmark set after processing
for record in fetch_records(start_date, end_date):
    singer.write_record(stream_name, record)
state["bookmarks"][stream_name] = {"updated_at": end_date}
singer.write_state(state)
```

### Anti-Pattern 2: No Lookback Window

```python
# WRONG: Sync starts exactly where it left off
start_date = state["bookmarks"][stream]["updated_at"]
```

**Fix:** Apply lookback window.

```python
# CORRECT: Lookback window for late-arriving data
bookmark = state["bookmarks"][stream]["updated_at"]
lookback_days = config.get("lookback_window", 7)
start_date = bookmark - timedelta(days=lookback_days)
```

### Anti-Pattern 3: State Only at End of Sync

```python
# WRONG: State emitted once after all records
all_records = fetch_all_records()
for record in all_records:
    singer.write_record(stream_name, record)
singer.write_state(state)  # 3-hour sync, state only at the very end
```

**Fix:** Emit state after each batch.

```python
# CORRECT: State emitted after each page/window
for page in paginate(endpoint):
    for record in page:
        singer.write_record(stream_name, record)
        update_bookmark(state, stream_name, record)
    singer.write_state(state)  # Checkpoint after each page
```

### Anti-Pattern 4: Child Bookmark Tied to Parent

```python
# WRONG: Child bookmark reset when parent is re-synced
for campaign in fetch_campaigns(since=campaign_bookmark):
    for ad_set in fetch_ad_sets(campaign_id=campaign["id"]):
        singer.write_record("ad_sets", ad_set)
    state["bookmarks"]["ad_sets"] = {"updated_at": now}  # Overwrites per-campaign
```

**Fix:** Independent child bookmarks with parent context.

```python
# CORRECT: Child bookmarks keyed by parent
for campaign in fetch_campaigns(since=campaign_bookmark):
    child_key = f"ad_sets__{campaign['id']}"
    child_bookmark = state["bookmarks"].get(child_key, {}).get("updated_at", start_date)
    for ad_set in fetch_ad_sets(campaign_id=campaign["id"], since=child_bookmark):
        singer.write_record("ad_sets", ad_set)
    state["bookmarks"][child_key] = {"updated_at": now}
    singer.write_state(state)
```

---

## Error Handling Decision Tree

```
Request failed
├── HTTP Status Code?
│   ├── 429 Too Many Requests
│   │   ├── Retry-After header present? → Sleep for Retry-After value
│   │   └── No Retry-After? → Exponential backoff (2^attempt * base, max 300s)
│   │       └── After max retries → FAIL with clear rate limit error
│   │
│   ├── 500 / 502 / 503 (Server Error)
│   │   ├── Attempt < max_retries? → Exponential backoff with jitter
│   │   └── Max retries exceeded
│   │       ├── Other streams remaining? → Log error, skip stream, continue
│   │       └── Last/only stream? → FAIL with error context
│   │
│   ├── 504 Gateway Timeout
│   │   ├── Attempt < 3? → Retry with smaller page/date range
│   │   └── Retries exhausted → FAIL (likely need to reduce query scope)
│   │
│   ├── 400 Bad Request
│   │   ├── Known transient 400? (some APIs return 400 for transient issues)
│   │   │   └── Retry once, then FAIL
│   │   └── Standard 400 → FAIL immediately (client error, won't fix on retry)
│   │
│   ├── 401 Unauthorized
│   │   ├── Token refresh available? → Refresh token, retry once
│   │   └── No refresh / refresh fails → FAIL (authentication issue)
│   │
│   ├── 403 Forbidden
│   │   └── FAIL immediately (permissions issue, needs manual intervention)
│   │
│   ├── 404 Not Found
│   │   ├── Entity-level request? → SKIP entity, log warning, continue
│   │   └── Stream-level endpoint? → FAIL (endpoint misconfigured)
│   │
│   └── Other 4xx → FAIL immediately with full response body in error
│
├── Connection Error?
│   ├── ConnectionError / ConnectionReset → Retry with backoff (max 3)
│   ├── Timeout → Retry with backoff (max 3), consider reducing page size
│   └── DNS resolution failure → FAIL (network/config issue)
│
└── Response Parsing Error?
    ├── JSON decode error → Log response body (truncated), retry once
    └── Unexpected response structure → Log and FAIL (API contract changed)
```

---

## Data Completeness Verification Patterns

### Record Count Validation

```python
def verify_page_completeness(response_data, expected_page_size):
    """Detect potentially incomplete pages."""
    actual_count = len(response_data.get("data", []))
    has_next = response_data.get("paging", {}).get("next") is not None

    if actual_count == 0 and has_next:
        logger.warning("Empty page with next cursor. Possible API inconsistency.")

    if actual_count < expected_page_size and has_next:
        logger.debug(f"Short page ({actual_count}/{expected_page_size}) with next cursor. Continuing.")

    return has_next
```

### Date Coverage Validation

```python
def verify_date_coverage(synced_dates, expected_start, expected_end):
    """Verify no gaps in date-windowed sync."""
    date_set = set(synced_dates)
    current = expected_start
    gaps = []
    while current <= expected_end:
        if current not in date_set:
            gaps.append(current)
        current += timedelta(days=1)

    if gaps:
        logger.warning(f"Date coverage gaps detected: {len(gaps)} missing days. "
                      f"First gap: {gaps[0]}, Last gap: {gaps[-1]}")
    return gaps
```

### Cross-Sync Reconciliation

```python
def log_sync_summary(stream_name, record_count, start_bookmark, end_bookmark, duration_seconds):
    """Log a reconciliation-friendly sync summary."""
    logger.info(
        f"SYNC_COMPLETE stream={stream_name} "
        f"records={record_count} "
        f"start_bookmark={start_bookmark} "
        f"end_bookmark={end_bookmark} "
        f"duration_seconds={duration_seconds:.1f} "
        f"records_per_second={record_count / max(duration_seconds, 1):.1f}"
    )
```

---

## Logging Best Practices for ETL Pipelines

### Log Levels

| Level | Use For | Example |
|---|---|---|
| DEBUG | Per-request details, per-record processing | `DEBUG: GET /v17.0/act_123/insights?date=2024-01-01 -> 200 (0.8s)` |
| INFO | Stream start/complete, sync summary, state emissions | `INFO: Stream 'ads' complete. 15,234 records in 180s.` |
| WARNING | Recoverable issues, approaching limits, data anomalies | `WARNING: Facebook API usage at 78%. Throttling.` |
| ERROR | Failed streams, exhausted retries, data issues | `ERROR: Stream 'ad_insights' failed after 5 retries. Last error: 500` |
| CRITICAL | Unrecoverable failures, credential issues | `CRITICAL: Access token expired and refresh failed.` |

### Structured Log Fields

Always include context in log messages:

```python
logger.info(
    "Stream sync complete",
    extra={
        "stream": stream_name,
        "record_count": count,
        "bookmark": bookmark_value,
        "duration_s": duration,
        "api_calls": api_call_count,
    }
)
```

### What NOT to Log

- Access tokens, API keys, or any credentials -- even at DEBUG level
- Full record payloads at INFO level (use DEBUG, and even then consider truncation)
- Every HTTP request at INFO level (use DEBUG)
- Stack traces for expected/handled errors (reserve for unexpected exceptions)

### What to ALWAYS Log

- Sync start with configuration summary (excluding credentials)
- Each stream start and completion with record count and duration
- State emissions (at DEBUG level)
- Rate limit throttling events
- Retry attempts with attempt number, error code, and sleep duration
- Final sync summary with total records, duration, and any skipped streams

---

## Facebook Marketing API Reliability Patterns

### 37-Month Data Retention

Facebook only stores data for approximately 37 months. Attempting to query older data returns empty results without an error.

```python
MAX_FACEBOOK_LOOKBACK_MONTHS = 37

def validate_start_date(config_start_date):
    earliest_allowed = datetime.now() - timedelta(days=MAX_FACEBOOK_LOOKBACK_MONTHS * 30)
    if config_start_date < earliest_allowed:
        logger.warning(
            f"Configured start_date {config_start_date} exceeds Facebook's "
            f"{MAX_FACEBOOK_LOOKBACK_MONTHS}-month retention limit. "
            f"Adjusting to {earliest_allowed.date()}"
        )
        return earliest_allowed
    return config_start_date
```

### Async Report Jobs for Insights

Large Insights queries should use async jobs to avoid timeouts.

```python
def fetch_insights_async(account, params, max_wait_seconds=1800):
    """Use async job for large date ranges."""
    job = account.get_insights(params=params, is_async=True)

    start_time = time.time()
    poll_interval = 5
    while True:
        job = job.api_get()
        status = job["async_status"]
        percent = job.get("async_percent_completion", 0)

        if status == "Job Completed":
            return job.get_result()

        if status == "Job Failed":
            raise FacebookInsightsJobFailed(f"Job {job['id']} failed: {job.get('async_status')}")

        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            raise FacebookInsightsJobTimeout(f"Job {job['id']} timed out after {elapsed:.0f}s at {percent}%")

        logger.debug(f"Insights job {job['id']}: {status} ({percent}%)")
        time.sleep(min(poll_interval, 60))
        poll_interval = min(poll_interval * 1.5, 60)  # Gradually increase poll interval
```

### Date Window Splitting on Failure

When an Insights job fails or times out, reduce the date range and retry.

```python
def fetch_insights_with_splitting(account, start_date, end_date, params, min_window_days=1):
    """Fetch insights, splitting date range on failure."""
    try:
        return fetch_insights_async(account, {**params, "time_range": {"since": start_date, "until": end_date}})
    except (FacebookInsightsJobFailed, FacebookInsightsJobTimeout):
        window_days = (end_date - start_date).days
        if window_days <= min_window_days:
            logger.error(f"Insights job failed for single-day window {start_date}. Skipping.")
            return []

        mid_date = start_date + timedelta(days=window_days // 2)
        logger.warning(f"Splitting date range [{start_date}, {end_date}] at {mid_date}")

        results_a = fetch_insights_with_splitting(account, start_date, mid_date, params)
        results_b = fetch_insights_with_splitting(account, mid_date + timedelta(days=1), end_date, params)
        return results_a + results_b
```

### Attribution Window Handling

```python
VALID_ATTRIBUTION_WINDOWS = ["1d_click", "7d_click", "28d_click", "1d_view", "7d_view", "28d_view"]

def build_action_attribution_params(config):
    windows = config.get("action_attribution_windows", ["7d_click", "1d_view"])
    for window in windows:
        if window not in VALID_ATTRIBUTION_WINDOWS:
            raise ConfigError(f"Invalid attribution window: {window}. Valid: {VALID_ATTRIBUTION_WINDOWS}")
    return {"action_attribution_windows": windows}
```

### Business Use Case Usage Headers

Always send the required headers and read the response headers.

```python
def make_facebook_request(session, url, params, access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    response = session.get(url, params=params, headers=headers, timeout=(10, 60))

    # Read rate limit usage from response
    throttle_facebook(response)

    response.raise_for_status()
    return response.json()
```

---

## Monitoring and Alerting Recommendations

### Key Metrics to Track

| Metric | Alert Threshold | Severity |
|---|---|---|
| Sync duration | > 2x historical average | WARNING |
| Record count per stream | < 50% of previous sync or zero | CRITICAL |
| Error rate (non-200 responses) | > 10% of total requests | WARNING |
| Rate limit events | > 20 per sync | INFO (consider optimization) |
| State age (time since last state emit) | > 30 minutes | WARNING |
| Memory usage | > 500MB | WARNING |
| Bookmark regression (bookmark went backward) | Any occurrence | CRITICAL |
| Schema change detected | Any new or removed field | INFO |

### Health Check Patterns

```python
def sync_health_check(sync_stats):
    """Post-sync health check for alerting."""
    issues = []

    for stream, stats in sync_stats.items():
        if stats["record_count"] == 0 and stats["expected_records"]:
            issues.append(f"CRITICAL: Stream '{stream}' returned 0 records (expected ~{stats['expected_records']})")

        if stats["error_count"] > stats["request_count"] * 0.1:
            issues.append(f"WARNING: Stream '{stream}' error rate {stats['error_count']}/{stats['request_count']}")

        if stats["duration_seconds"] > stats["historical_avg_seconds"] * 3:
            issues.append(f"WARNING: Stream '{stream}' took {stats['duration_seconds']:.0f}s (3x average)")

    return issues
```

---

## Recovery Procedures

### Procedure 1: Recovering from a Corrupted State File

1. Examine the state file for obvious issues (malformed JSON, impossible bookmark values).
2. If the state references nonexistent streams, remove those entries.
3. If a bookmark value is in the future, reset it to the current time.
4. If a bookmark value is suspiciously old, consider whether a lookback window covers the gap.
5. If state is unrecoverable, delete it and run a full sync. Set `start_date` in config to limit the scope.

### Procedure 2: Recovering from a Partial Sync Failure

1. Check the last emitted state (usually in the target's state file or Meltano's system database).
2. Verify the state contains valid bookmarks for completed streams.
3. Restart the sync with the existing state. Successfully completed streams will skip ahead; the failed stream will resume from its last bookmark.
4. If the failed stream consistently fails at the same point, investigate the specific error and consider:
   - Reducing the page size or date window
   - Skipping the problematic record/date range
   - Contacting the API provider

### Procedure 3: Recovering from Rate Limit Lockout

1. Check the API dashboard for current rate limit status and reset time.
2. Wait for the rate limit to reset completely (do not retry immediately).
3. Before restarting, review the tap's rate limiting configuration and increase throttling.
4. Consider reducing the number of selected streams or fields to reduce API call volume.
5. Restart the sync from existing state.

### Procedure 4: Recovering from Schema Change

1. Run `--discover` to get the current schema from the API.
2. Compare with the catalog used by the last sync.
3. If fields were added: update the catalog, the new fields will be populated from the next sync onward.
4. If fields were removed: update the catalog to remove references. Downstream may need ALTER TABLE or schema migration.
5. If field types changed: this is the most dangerous. Check downstream for type conflicts. May need to recreate the destination table.
6. Restart the sync with the updated catalog.

### Procedure 5: Data Gap Recovery

1. Identify the gap: query the destination for the missing date range or record IDs.
2. Create a temporary config with `start_date` set to the beginning of the gap.
3. Create a temporary state with the bookmark set to just before the gap.
4. Run a recovery sync with this temporary state.
5. Verify the gap is filled by re-querying the destination.
6. Restore the original state (with the latest bookmark) and resume normal syncs.
