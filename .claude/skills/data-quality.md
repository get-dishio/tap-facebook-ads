---
name: data-quality
description: Data quality validation, schema evolution, completeness checks, and anomaly detection for ETL pipelines
---

# Data Quality Reference for ETL Pipelines

Comprehensive patterns and practices for validating, monitoring, and maintaining data quality in Singer/Meltano tap pipelines.

---

## Schema Validation Patterns

### Strict Validation

Reject records that do not conform to the declared schema. Best for pipelines where data integrity is paramount and you would rather fail loudly than ingest bad data.

```python
import jsonschema

def validate_record_strict(record, schema):
    """Validate a record against its JSON Schema. Raises on any violation."""
    try:
        jsonschema.validate(instance=record, schema=schema)
    except jsonschema.ValidationError as e:
        raise DataQualityError(
            f"Record failed schema validation: {e.message}. "
            f"Path: {'.'.join(str(p) for p in e.absolute_path)}. "
            f"Record ID: {record.get('id', 'unknown')}"
        )
```

**When to use:** Financial data, compliance-regulated data, pipelines where downstream consumers have strict schema expectations (e.g., typed data warehouses).

**Tradeoffs:** Will halt the sync on the first bad record. May cause issues when APIs add new fields or change types without warning.

### Permissive Validation

Accept records that mostly conform, logging warnings for deviations. Best for pipelines where data availability is more important than perfect conformance.

```python
def validate_record_permissive(record, schema, stream_name):
    """Validate a record, logging warnings but not failing."""
    errors = []
    validator = jsonschema.Draft7Validator(schema)

    for error in validator.iter_errors(record):
        errors.append({
            "path": ".".join(str(p) for p in error.absolute_path),
            "message": error.message,
            "value": error.instance,
        })

    if errors:
        logger.warning(
            f"Record in stream '{stream_name}' has {len(errors)} schema violations. "
            f"Record ID: {record.get('id', 'unknown')}. "
            f"First violation: {errors[0]['path']}: {errors[0]['message']}"
        )

    return record, errors
```

**When to use:** Analytics data, APIs known to evolve frequently, pipelines where missing a few fields is acceptable but losing records is not.

**Tradeoffs:** Bad data may silently flow downstream. Requires downstream handling of unexpected types or missing fields.

### Coercive Validation

Attempt to coerce values to the expected type before validating. Falls between strict and permissive.

```python
def coerce_record(record, schema):
    """Attempt to coerce record values to match schema types."""
    properties = schema.get("properties", {})
    coerced = {}

    for field, value in record.items():
        if field not in properties:
            coerced[field] = value
            continue

        field_schema = properties[field]
        expected_types = field_schema.get("type", [])
        if isinstance(expected_types, str):
            expected_types = [expected_types]

        coerced[field] = coerce_value(value, expected_types, field)

    return coerced

def coerce_value(value, expected_types, field_name):
    """Coerce a value to one of the expected types."""
    if value is None:
        if "null" in expected_types:
            return None
        logger.warning(f"Field '{field_name}': null value but null not in schema types {expected_types}")
        return None  # Pass through; downstream can decide

    if "string" in expected_types and not isinstance(value, str):
        return str(value)

    if "integer" in expected_types and isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Field '{field_name}': cannot coerce '{value}' to integer")
            return value

    if "number" in expected_types and isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Field '{field_name}': cannot coerce '{value}' to number")
            return value

    if "boolean" in expected_types and isinstance(value, str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no", ""):
            return False

    return value
```

---

## Type Coercion Rules and Null Handling

### Coercion Priority Matrix

When a value does not match the expected type, apply coercion rules in this priority order:

| Source Type | Target Type | Rule | Example |
|---|---|---|---|
| `int` | `string` | Always safe | `42` -> `"42"` |
| `float` | `string` | Always safe | `3.14` -> `"3.14"` |
| `bool` | `string` | Always safe | `true` -> `"true"` |
| `string` | `int` | Attempt parse, null on failure | `"42"` -> `42`, `"abc"` -> `null` |
| `string` | `float` | Attempt parse, null on failure | `"3.14"` -> `3.14`, `"abc"` -> `null` |
| `string` | `bool` | Map known values, null on unknown | `"true"` -> `true`, `"xyz"` -> `null` |
| `string` | `datetime` | Attempt ISO 8601 parse, null on failure | `"2024-01-01T00:00:00Z"` -> datetime |
| `int` | `float` | Always safe (widen) | `42` -> `42.0` |
| `float` | `int` | Truncate if no precision loss, else null | `42.0` -> `42`, `42.5` -> `null` + warning |
| `null` | any | Pass through if nullable, default or warn if not | |

### Null Handling Rules

```python
class NullHandlingStrategy:
    """Strategies for handling null values in non-nullable fields."""

    @staticmethod
    def strict(field_name, schema_type):
        """Raise an error on null in non-nullable field."""
        raise DataQualityError(f"Null value in non-nullable field '{field_name}' (type: {schema_type})")

    @staticmethod
    def default_value(field_name, schema_type):
        """Replace null with a type-appropriate default."""
        defaults = {
            "string": "",
            "integer": 0,
            "number": 0.0,
            "boolean": False,
            "array": [],
            "object": {},
        }
        if isinstance(schema_type, list):
            schema_type = [t for t in schema_type if t != "null"][0] if len(schema_type) > 1 else schema_type[0]
        return defaults.get(schema_type)

    @staticmethod
    def passthrough(field_name, schema_type):
        """Pass null through regardless of schema. Let downstream handle it."""
        return None
```

### Recommended null handling by context

| Context | Strategy | Rationale |
|---|---|---|
| Primary key fields | Strict | A null PK breaks deduplication and merge logic |
| Replication key fields | Strict | A null bookmark breaks incremental sync |
| Metric fields (counts, amounts) | Default to 0 | Null metrics cause SUM/AVG errors downstream |
| Dimension fields (names, labels) | Passthrough | Nulls are valid for optional dimensions |
| Nested objects | Passthrough | Null nested objects are common in sparse APIs |
| Boolean flags | Default to false | Null booleans break WHERE clauses |

---

## Completeness Metrics

### Record Count Tracking

```python
class CompletenessTracker:
    """Track data completeness metrics during a sync."""

    def __init__(self):
        self.stream_counts = {}
        self.stream_date_coverage = {}
        self.stream_field_population = {}

    def track_record(self, stream_name, record, replication_key=None):
        # Track record count
        self.stream_counts.setdefault(stream_name, 0)
        self.stream_counts[stream_name] += 1

        # Track date coverage
        if replication_key and replication_key in record:
            date_value = record[replication_key]
            if isinstance(date_value, str):
                date_value = date_value[:10]  # Extract date portion
            self.stream_date_coverage.setdefault(stream_name, set())
            self.stream_date_coverage[stream_name].add(date_value)

        # Track field population rates
        self.stream_field_population.setdefault(stream_name, {})
        for field, value in record.items():
            self.stream_field_population[stream_name].setdefault(field, {"total": 0, "populated": 0})
            self.stream_field_population[stream_name][field]["total"] += 1
            if value is not None and value != "" and value != []:
                self.stream_field_population[stream_name][field]["populated"] += 1

    def get_summary(self, stream_name):
        count = self.stream_counts.get(stream_name, 0)
        dates = self.stream_date_coverage.get(stream_name, set())
        fields = self.stream_field_population.get(stream_name, {})

        population_rates = {}
        for field, stats in fields.items():
            rate = stats["populated"] / stats["total"] if stats["total"] > 0 else 0
            population_rates[field] = round(rate * 100, 1)

        return {
            "record_count": count,
            "date_range": (min(dates), max(dates)) if dates else None,
            "unique_dates": len(dates),
            "field_population_rates": population_rates,
            "sparse_fields": [f for f, r in population_rates.items() if r < 10.0],
        }
```

### Completeness Assertions

```python
def assert_completeness(tracker, stream_name, expected_start, expected_end, min_records=1):
    """Assert minimum completeness requirements. Raises on failure."""
    summary = tracker.get_summary(stream_name)

    # Must have at least some records
    if summary["record_count"] < min_records:
        raise DataCompletenessError(
            f"Stream '{stream_name}': expected at least {min_records} records, got {summary['record_count']}"
        )

    # Date coverage check
    if summary["date_range"]:
        actual_start, actual_end = summary["date_range"]
        if actual_start > expected_start:
            logger.warning(
                f"Stream '{stream_name}': data starts at {actual_start}, "
                f"expected {expected_start}. Possible gap."
            )
        if actual_end < expected_end:
            logger.warning(
                f"Stream '{stream_name}': data ends at {actual_end}, "
                f"expected {expected_end}. Possible lag."
            )

    # Sparse field warnings
    if summary["sparse_fields"]:
        logger.info(
            f"Stream '{stream_name}': {len(summary['sparse_fields'])} fields "
            f"with <10% population: {summary['sparse_fields'][:5]}"
        )
```

---

## Freshness Monitoring

### Freshness Metadata

```python
from datetime import datetime, timezone

class FreshnessMonitor:
    """Track data freshness per stream."""

    def __init__(self):
        self.stream_freshness = {}

    def update(self, stream_name, record, replication_key):
        """Update freshness tracking with a new record."""
        if replication_key not in record:
            return

        record_time = self._parse_datetime(record[replication_key])
        if record_time is None:
            return

        current = self.stream_freshness.get(stream_name)
        if current is None or record_time > current:
            self.stream_freshness[stream_name] = record_time

    def get_freshness(self, stream_name):
        """Get freshness info for a stream."""
        latest = self.stream_freshness.get(stream_name)
        if latest is None:
            return {"latest_record": None, "lag_seconds": None, "status": "NO_DATA"}

        now = datetime.now(timezone.utc)
        lag = (now - latest).total_seconds()

        status = "FRESH"
        if lag > 86400:  # 24 hours
            status = "STALE"
        elif lag > 3600:  # 1 hour
            status = "DELAYED"

        return {
            "latest_record": latest.isoformat(),
            "lag_seconds": lag,
            "lag_human": self._humanize_duration(lag),
            "status": status,
        }

    @staticmethod
    def _parse_datetime(value):
        """Best-effort datetime parsing."""
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _humanize_duration(seconds):
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            return f"{seconds / 60:.0f}m"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"
```

### Freshness Thresholds by Stream Type

| Stream Type | Expected Freshness | DELAYED Threshold | STALE Threshold |
|---|---|---|---|
| Real-time event streams | < 5 minutes | > 15 minutes | > 1 hour |
| Hourly aggregates (e.g., ad insights) | < 2 hours | > 6 hours | > 24 hours |
| Daily snapshots (e.g., campaign status) | < 24 hours | > 36 hours | > 72 hours |
| Static reference data (e.g., custom audiences) | < 7 days | > 14 days | > 30 days |
| Historical backfill | N/A | N/A | N/A |

---

## Duplicate Detection Strategies

### Primary Key Deduplication

```python
class DuplicateDetector:
    """Detect duplicate records within a sync using primary keys."""

    def __init__(self, key_properties):
        self.key_properties = key_properties
        self._seen_keys = set()
        self.duplicate_count = 0

    def check(self, record):
        """Check if a record is a duplicate. Returns True if duplicate."""
        if not self.key_properties:
            return False  # Cannot detect duplicates without key properties

        key = tuple(record.get(k) for k in self.key_properties)

        if None in key:
            logger.warning(
                f"Record has null primary key component. "
                f"Key properties: {self.key_properties}, values: {key}"
            )
            return False  # Cannot determine uniqueness

        if key in self._seen_keys:
            self.duplicate_count += 1
            return True

        self._seen_keys.add(key)
        return False

    def get_stats(self):
        return {
            "unique_records": len(self._seen_keys),
            "duplicate_records": self.duplicate_count,
            "duplicate_rate": (
                self.duplicate_count / (len(self._seen_keys) + self.duplicate_count)
                if (len(self._seen_keys) + self.duplicate_count) > 0
                else 0
            ),
        }
```

### Expected Duplicate Scenarios

Not all duplicates are bugs. Some are expected and should be documented:

| Scenario | Expected? | Handling |
|---|---|---|
| Overlapping lookback windows | Yes | Downstream deduplicates on PK. Normal for incremental syncs with lookback. |
| Pagination overlap (cursor instability) | Possible | Log warning. May indicate an API bug or concurrent data mutation. |
| Parent-child fan-out | No (usually a bug) | If a child record appears under multiple parents, investigate the data model. |
| Full sync re-run | Yes | Full replacement at destination. No dedup needed. |
| API returning same record twice on same page | Bug (API-side) | Deduplicate in tap. Log warning. |

### Memory-Efficient Deduplication for Large Streams

For streams with millions of records, keeping all keys in memory may be impractical. Use a probabilistic approach.

```python
import hashlib

class BloomFilterDeduplicator:
    """Memory-efficient probabilistic duplicate detection.

    Uses a simple hash-based approach. False positives are possible
    (marking a unique record as duplicate) but false negatives are not
    (a true duplicate will always be detected).
    """

    def __init__(self, expected_count, false_positive_rate=0.001):
        import math
        self.size = int(-expected_count * math.log(false_positive_rate) / (math.log(2) ** 2))
        self.hash_count = int((self.size / expected_count) * math.log(2))
        self.bit_array = bytearray(self.size // 8 + 1)
        self.duplicate_count = 0

    def _hashes(self, key_string):
        for i in range(self.hash_count):
            h = hashlib.md5(f"{key_string}:{i}".encode()).hexdigest()
            yield int(h, 16) % self.size

    def check(self, record, key_properties):
        key_string = "|".join(str(record.get(k, "")) for k in key_properties)
        positions = list(self._hashes(key_string))

        is_probably_duplicate = all(
            self.bit_array[pos // 8] & (1 << (pos % 8))
            for pos in positions
        )

        for pos in positions:
            self.bit_array[pos // 8] |= (1 << (pos % 8))

        if is_probably_duplicate:
            self.duplicate_count += 1

        return is_probably_duplicate
```

---

## Schema Evolution Handling

### Detecting Schema Changes

```python
def detect_schema_changes(previous_schema, current_schema):
    """Compare two schemas and report changes."""
    changes = {
        "added_fields": [],
        "removed_fields": [],
        "type_changes": [],
        "nullability_changes": [],
    }

    prev_props = previous_schema.get("properties", {})
    curr_props = current_schema.get("properties", {})

    # Detect added fields
    for field in curr_props:
        if field not in prev_props:
            changes["added_fields"].append({
                "field": field,
                "type": curr_props[field].get("type"),
            })

    # Detect removed fields
    for field in prev_props:
        if field not in curr_props:
            changes["removed_fields"].append({
                "field": field,
                "type": prev_props[field].get("type"),
            })

    # Detect type and nullability changes
    for field in prev_props:
        if field in curr_props:
            prev_type = prev_props[field].get("type", [])
            curr_type = curr_props[field].get("type", [])

            if isinstance(prev_type, str):
                prev_type = [prev_type]
            if isinstance(curr_type, str):
                curr_type = [curr_type]

            prev_non_null = set(t for t in prev_type if t != "null")
            curr_non_null = set(t for t in curr_type if t != "null")

            if prev_non_null != curr_non_null:
                changes["type_changes"].append({
                    "field": field,
                    "previous_type": sorted(prev_non_null),
                    "current_type": sorted(curr_non_null),
                })

            prev_nullable = "null" in prev_type
            curr_nullable = "null" in curr_type
            if prev_nullable != curr_nullable:
                changes["nullability_changes"].append({
                    "field": field,
                    "was_nullable": prev_nullable,
                    "is_nullable": curr_nullable,
                })

    return changes
```

### Schema Evolution Strategies

| Change Type | Strategy | Risk Level | Action |
|---|---|---|---|
| New field added | Add to schema, emit as nullable | LOW | Auto-handle. Log at INFO. |
| Field removed from API | Keep in schema as nullable, emit nulls | LOW | Log at WARNING. May remove in next major version. |
| Type widened (int -> float) | Update schema type | LOW | Auto-handle. Downstream may need migration. |
| Type narrowed (float -> int) | Keep wider type in schema, coerce | MEDIUM | Log at WARNING. Verify no precision loss. |
| Type changed (string -> int) | Keep both types in schema (`["string", "integer"]`) | HIGH | Log at WARNING. Downstream must handle. |
| Nullable -> non-nullable | Keep nullable in schema | LOW | Log at INFO. Safer to keep nullable. |
| Non-nullable -> nullable | Update schema to nullable | MEDIUM | Log at WARNING. Downstream NULL handling needed. |
| Field renamed | Emit both old (null) and new field | HIGH | Log at WARNING. Requires manual migration plan. |
| Nested object structure changed | Depends on depth of change | HIGH | Log at ERROR. May require manual intervention. |

### Implementing Safe Schema Evolution

```python
class SchemaEvolver:
    """Manage schema evolution safely during sync."""

    def __init__(self, declared_schema, stream_name):
        self.declared_schema = declared_schema
        self.stream_name = stream_name
        self.undeclared_fields_seen = set()
        self.type_mismatches_seen = {}

    def process_record(self, record):
        """Process a record, handling schema deviations."""
        processed = {}
        declared_props = self.declared_schema.get("properties", {})

        for field, value in record.items():
            if field not in declared_props:
                if field not in self.undeclared_fields_seen:
                    self.undeclared_fields_seen.add(field)
                    logger.warning(
                        f"Stream '{self.stream_name}': undeclared field '{field}' "
                        f"with type {type(value).__name__}. Including in output."
                    )
                processed[field] = value
                continue

            expected_types = declared_props[field].get("type", [])
            if isinstance(expected_types, str):
                expected_types = [expected_types]

            if not self._type_matches(value, expected_types):
                mismatch_key = f"{field}:{type(value).__name__}"
                if mismatch_key not in self.type_mismatches_seen:
                    self.type_mismatches_seen[mismatch_key] = 0
                    logger.warning(
                        f"Stream '{self.stream_name}': field '{field}' has value "
                        f"of type {type(value).__name__}, expected {expected_types}. "
                        f"Attempting coercion."
                    )
                self.type_mismatches_seen[mismatch_key] += 1
                processed[field] = self._coerce(value, expected_types)
            else:
                processed[field] = value

        # Include declared fields with null default if missing from record
        for field in declared_props:
            if field not in processed:
                processed[field] = None

        return processed

    @staticmethod
    def _type_matches(value, expected_types):
        if value is None:
            return "null" in expected_types
        type_map = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
        python_type = type_map.get(type(value))
        if python_type in expected_types:
            return True
        # int is also valid for "number"
        if isinstance(value, int) and "number" in expected_types:
            return True
        return False

    @staticmethod
    def _coerce(value, expected_types):
        non_null_types = [t for t in expected_types if t != "null"]
        if not non_null_types:
            return None
        target = non_null_types[0]
        try:
            if target == "string":
                return str(value)
            if target == "integer":
                return int(value)
            if target == "number":
                return float(value)
            if target == "boolean":
                return bool(value)
        except (ValueError, TypeError):
            return None
        return value
```

---

## Data Reconciliation Patterns

### Source-to-Destination Count Reconciliation

```python
def reconcile_counts(source_counts, destination_counts, tolerance_pct=5.0):
    """Compare record counts between source and destination.

    Args:
        source_counts: dict of {stream_name: record_count} from the tap
        destination_counts: dict of {stream_name: record_count} from the target
        tolerance_pct: acceptable percentage difference

    Returns:
        List of discrepancy findings
    """
    findings = []

    for stream, source_count in source_counts.items():
        dest_count = destination_counts.get(stream)

        if dest_count is None:
            findings.append({
                "stream": stream,
                "severity": "CRITICAL",
                "message": f"Stream '{stream}' has {source_count} source records but is missing from destination",
            })
            continue

        if source_count == 0 and dest_count == 0:
            continue

        diff = abs(source_count - dest_count)
        diff_pct = (diff / max(source_count, 1)) * 100

        if diff_pct > tolerance_pct:
            severity = "CRITICAL" if diff_pct > 20 else "HIGH" if diff_pct > 10 else "MEDIUM"
            findings.append({
                "stream": stream,
                "severity": severity,
                "message": (
                    f"Stream '{stream}': source={source_count}, destination={dest_count}, "
                    f"difference={diff} ({diff_pct:.1f}%)"
                ),
                "source_count": source_count,
                "destination_count": dest_count,
                "difference": diff,
                "difference_pct": diff_pct,
            })

    # Check for streams in destination but not in source
    for stream in destination_counts:
        if stream not in source_counts:
            findings.append({
                "stream": stream,
                "severity": "WARNING",
                "message": f"Stream '{stream}' exists in destination but not in source sync",
            })

    return findings
```

### Bookmark Reconciliation

```python
def reconcile_bookmarks(state, destination_max_values, streams_config):
    """Verify bookmark values are consistent with destination data.

    Detects cases where bookmark has advanced past what's actually in the destination
    (indicating data loss) or where destination has newer data than the bookmark
    (indicating state file is stale).
    """
    findings = []

    for stream_name, bookmark_info in state.get("bookmarks", {}).items():
        config = streams_config.get(stream_name, {})
        replication_key = config.get("replication_key")
        if not replication_key:
            continue

        bookmark_value = bookmark_info.get(replication_key)
        dest_max = destination_max_values.get(stream_name, {}).get(replication_key)

        if bookmark_value and dest_max:
            if bookmark_value > dest_max:
                findings.append({
                    "stream": stream_name,
                    "severity": "CRITICAL",
                    "message": (
                        f"Bookmark ({bookmark_value}) is ahead of destination max ({dest_max}). "
                        f"Data may have been lost between these values."
                    ),
                })
            elif dest_max > bookmark_value:
                findings.append({
                    "stream": stream_name,
                    "severity": "WARNING",
                    "message": (
                        f"Destination max ({dest_max}) is ahead of bookmark ({bookmark_value}). "
                        f"State file may be stale."
                    ),
                })

    return findings
```

---

## Anomaly Detection

### Volume Anomaly Detection

```python
import statistics

class VolumeAnomalyDetector:
    """Detect anomalies in sync volume based on historical patterns."""

    def __init__(self, historical_counts, sensitivity=2.0):
        """
        Args:
            historical_counts: list of record counts from previous syncs
            sensitivity: number of standard deviations for anomaly threshold
        """
        self.historical_counts = historical_counts
        self.sensitivity = sensitivity

        if len(historical_counts) >= 3:
            self.mean = statistics.mean(historical_counts)
            self.stdev = statistics.stdev(historical_counts)
        else:
            self.mean = None
            self.stdev = None

    def check(self, current_count):
        """Check if current count is anomalous."""
        if self.mean is None:
            return {"anomaly": False, "reason": "Insufficient history for anomaly detection"}

        if self.stdev == 0:
            # All historical values are the same
            if current_count != self.mean:
                return {
                    "anomaly": True,
                    "severity": "WARNING",
                    "reason": f"Count {current_count} deviates from constant historical value {self.mean}",
                    "z_score": float("inf") if current_count > self.mean else float("-inf"),
                }
            return {"anomaly": False}

        z_score = (current_count - self.mean) / self.stdev

        if abs(z_score) > self.sensitivity:
            direction = "spike" if z_score > 0 else "drop"
            severity = "CRITICAL" if abs(z_score) > 3 * self.sensitivity else "HIGH" if abs(z_score) > 2 * self.sensitivity else "WARNING"

            return {
                "anomaly": True,
                "severity": severity,
                "direction": direction,
                "reason": (
                    f"Volume {direction}: {current_count} records "
                    f"(mean={self.mean:.0f}, stdev={self.stdev:.0f}, z-score={z_score:.1f})"
                ),
                "z_score": z_score,
                "expected_range": (
                    max(0, self.mean - self.sensitivity * self.stdev),
                    self.mean + self.sensitivity * self.stdev,
                ),
            }

        return {"anomaly": False, "z_score": z_score}
```

### Schema Drift Detection

```python
class SchemaDriftDetector:
    """Detect gradual schema changes across syncs."""

    def __init__(self):
        self.field_type_history = {}  # field -> [list of observed types]
        self.field_first_seen = {}
        self.field_last_seen = {}

    def observe(self, stream_name, schema, sync_id):
        """Record observed schema for a sync."""
        properties = schema.get("properties", {})

        for field, field_schema in properties.items():
            key = f"{stream_name}.{field}"
            field_type = field_schema.get("type", "unknown")
            if isinstance(field_type, list):
                field_type = tuple(sorted(field_type))
            else:
                field_type = (field_type,)

            self.field_type_history.setdefault(key, [])
            self.field_type_history[key].append({"sync_id": sync_id, "type": field_type})

            if key not in self.field_first_seen:
                self.field_first_seen[key] = sync_id
            self.field_last_seen[key] = sync_id

    def detect_drift(self, stream_name):
        """Detect schema drift patterns."""
        findings = []
        prefix = f"{stream_name}."

        for key, history in self.field_type_history.items():
            if not key.startswith(prefix):
                continue

            field_name = key[len(prefix):]
            types_observed = set(entry["type"] for entry in history)

            if len(types_observed) > 1:
                findings.append({
                    "field": field_name,
                    "severity": "HIGH",
                    "type": "type_drift",
                    "message": (
                        f"Field '{field_name}' has been observed with multiple types: "
                        f"{[list(t) for t in types_observed]}"
                    ),
                    "history": history,
                })

        # Detect recently appeared fields (may indicate API evolution)
        all_sync_ids = set()
        for history in self.field_type_history.values():
            for entry in history:
                all_sync_ids.add(entry["sync_id"])

        if len(all_sync_ids) > 1:
            latest_sync = max(all_sync_ids)
            for key, first_sync in self.field_first_seen.items():
                if key.startswith(prefix) and first_sync == latest_sync:
                    field_name = key[len(prefix):]
                    findings.append({
                        "field": field_name,
                        "severity": "INFO",
                        "type": "new_field",
                        "message": f"Field '{field_name}' first appeared in the latest sync",
                    })

        return findings
```

### Value Distribution Anomaly

```python
def check_value_distribution(field_name, current_values, historical_distribution):
    """Check if value distribution has shifted significantly.

    Useful for categorical fields (e.g., ad status, campaign objective).
    """
    findings = []

    current_distribution = {}
    for v in current_values:
        current_distribution[v] = current_distribution.get(v, 0) + 1
    total = sum(current_distribution.values())
    current_pcts = {k: (v / total) * 100 for k, v in current_distribution.items()}

    # Check for new values not seen historically
    for value in current_pcts:
        if value not in historical_distribution:
            findings.append({
                "field": field_name,
                "severity": "INFO",
                "type": "new_value",
                "message": f"New value '{value}' for field '{field_name}' ({current_pcts[value]:.1f}%)",
            })

    # Check for large distribution shifts
    for value, hist_pct in historical_distribution.items():
        curr_pct = current_pcts.get(value, 0)
        shift = abs(curr_pct - hist_pct)
        if shift > 20:  # More than 20 percentage point shift
            findings.append({
                "field": field_name,
                "severity": "WARNING",
                "type": "distribution_shift",
                "message": (
                    f"Field '{field_name}', value '{value}': "
                    f"shifted from {hist_pct:.1f}% to {curr_pct:.1f}% ({shift:+.1f}pp)"
                ),
            })

    # Check for disappeared values
    for value, hist_pct in historical_distribution.items():
        if value not in current_pcts and hist_pct > 5:
            findings.append({
                "field": field_name,
                "severity": "WARNING",
                "type": "missing_value",
                "message": (
                    f"Value '{value}' for field '{field_name}' was {hist_pct:.1f}% "
                    f"historically but is absent in current sync"
                ),
            })

    return findings
```

---

## Testing Patterns for Data Quality

### Test Fixtures

```python
import pytest

@pytest.fixture
def valid_record():
    """A record that conforms to the schema."""
    return {
        "id": "12345",
        "name": "Test Campaign",
        "status": "ACTIVE",
        "daily_budget": 1000,
        "created_time": "2024-01-15T10:30:00Z",
    }

@pytest.fixture
def schema():
    """Standard schema for testing."""
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": ["string", "null"]},
            "status": {"type": "string"},
            "daily_budget": {"type": ["integer", "null"]},
            "created_time": {"type": "string", "format": "date-time"},
        },
        "required": ["id"],
    }
```

### Schema Validation Tests

```python
class TestSchemaValidation:
    def test_valid_record_passes(self, valid_record, schema):
        errors = validate_record_permissive(valid_record, schema, "test_stream")
        assert len(errors[1]) == 0

    def test_extra_field_in_record(self, valid_record, schema):
        valid_record["new_api_field"] = "surprise"
        record, errors = validate_record_permissive(valid_record, schema, "test_stream")
        # Permissive should pass; strict should fail
        assert "new_api_field" in record

    def test_wrong_type_detected(self, valid_record, schema):
        valid_record["daily_budget"] = "not_a_number"
        record, errors = validate_record_permissive(valid_record, schema, "test_stream")
        assert len(errors) > 0

    def test_null_in_nullable_field(self, valid_record, schema):
        valid_record["name"] = None
        record, errors = validate_record_permissive(valid_record, schema, "test_stream")
        assert len(errors) == 0

    def test_null_in_required_field(self, valid_record, schema):
        valid_record["id"] = None
        record, errors = validate_record_permissive(valid_record, schema, "test_stream")
        assert len(errors) > 0

    def test_missing_required_field(self, schema):
        record = {"name": "No ID"}
        record, errors = validate_record_permissive(record, schema, "test_stream")
        assert len(errors) > 0
```

### Completeness Tests

```python
class TestCompleteness:
    def test_record_count_tracking(self):
        tracker = CompletenessTracker()
        for i in range(100):
            tracker.track_record("test_stream", {"id": str(i), "date": "2024-01-15"})
        summary = tracker.get_summary("test_stream")
        assert summary["record_count"] == 100

    def test_date_coverage_gaps(self):
        tracker = CompletenessTracker()
        # Simulate records for Jan 1-3 and Jan 5-7 (gap on Jan 4)
        for day in [1, 2, 3, 5, 6, 7]:
            tracker.track_record(
                "test_stream",
                {"id": str(day), "date": f"2024-01-0{day}"},
                replication_key="date",
            )
        summary = tracker.get_summary("test_stream")
        assert summary["unique_dates"] == 6  # 7 days minus the gap

    def test_field_population_rates(self):
        tracker = CompletenessTracker()
        for i in range(10):
            record = {"id": str(i), "name": f"name_{i}" if i < 8 else None}
            tracker.track_record("test_stream", record)
        summary = tracker.get_summary("test_stream")
        assert summary["field_population_rates"]["name"] == 80.0
```

### Duplicate Detection Tests

```python
class TestDuplicateDetection:
    def test_no_duplicates(self):
        detector = DuplicateDetector(["id"])
        for i in range(100):
            assert detector.check({"id": str(i)}) is False
        assert detector.get_stats()["duplicate_records"] == 0

    def test_duplicate_detected(self):
        detector = DuplicateDetector(["id"])
        assert detector.check({"id": "1"}) is False
        assert detector.check({"id": "1"}) is True
        assert detector.get_stats()["duplicate_records"] == 1

    def test_compound_key_duplicates(self):
        detector = DuplicateDetector(["campaign_id", "date"])
        assert detector.check({"campaign_id": "1", "date": "2024-01-01"}) is False
        assert detector.check({"campaign_id": "1", "date": "2024-01-02"}) is False
        assert detector.check({"campaign_id": "1", "date": "2024-01-01"}) is True

    def test_null_key_not_flagged_as_duplicate(self):
        detector = DuplicateDetector(["id"])
        assert detector.check({"id": None}) is False
        assert detector.check({"id": None}) is False  # Null keys are not tracked
```

### Anomaly Detection Tests

```python
class TestAnomalyDetection:
    def test_normal_volume(self):
        detector = VolumeAnomalyDetector([100, 105, 95, 102, 98])
        result = detector.check(103)
        assert result["anomaly"] is False

    def test_volume_spike(self):
        detector = VolumeAnomalyDetector([100, 105, 95, 102, 98])
        result = detector.check(500)
        assert result["anomaly"] is True
        assert result["direction"] == "spike"

    def test_volume_drop(self):
        detector = VolumeAnomalyDetector([100, 105, 95, 102, 98])
        result = detector.check(5)
        assert result["anomaly"] is True
        assert result["direction"] == "drop"

    def test_insufficient_history(self):
        detector = VolumeAnomalyDetector([100])
        result = detector.check(500)
        assert result["anomaly"] is False
        assert "Insufficient" in result["reason"]

    def test_zero_volume_critical(self):
        detector = VolumeAnomalyDetector([100, 105, 95, 102, 98])
        result = detector.check(0)
        assert result["anomaly"] is True
        assert result["severity"] in ("CRITICAL", "HIGH")
```

---

## Quick Reference: Data Quality Checks by Pipeline Stage

### Pre-Sync (Config/Discovery)

- Validate configuration fields (required, types, ranges)
- Verify API credentials are valid
- Run discovery and compare schema to expected
- Check that selected streams exist in the catalog
- Validate replication keys exist in schemas

### During Sync (Per-Record)

- Validate record against schema (strict or permissive)
- Check for null primary keys
- Track field population rates
- Detect duplicates (if key_properties set)
- Coerce types where safe

### During Sync (Per-Batch/Page)

- Log record count per page
- Verify pagination has not looped
- Emit state checkpoint
- Track cumulative record counts

### During Sync (Per-Stream)

- Log total record count and duration
- Compare count to historical average
- Verify date coverage (for date-windowed streams)
- Report sparse fields
- Report duplicate stats

### Post-Sync

- Log final sync summary (all streams)
- Compare total counts to previous syncs
- Verify all selected streams were synced
- Report freshness per stream
- Emit final state
- Run reconciliation against destination (if possible)
