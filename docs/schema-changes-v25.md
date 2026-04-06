# Schema Changes: v21 → v25 Migration — Downstream Impact Assessment

**Branch**: `fb-marketing-api-v25-upgrade`
**Date**: 2026-03-16
**API Version**: Facebook Marketing API v21.0 → v25.0

---

## Summary

This migration removes 11 fields across 3 streams, renames 1 field, and removes 1 duplicate. Any downstream systems (targets, warehouses, BI tools, transformation scripts) that depend on these fields will need to be updated.

---

## REMOVED Fields (will no longer appear in output)

### Ads Stream (`ads`)

| Field | Type | Reason | Downstream Impact |
|-------|------|--------|-------------------|
| `bid_type` | `string` | Removed from Facebook API v25 | Drop column from target tables. Any reports filtering/grouping by bid_type will break. |
| `bid_info` | `object` (CLICKS, ACTIONS, REACH, IMPRESSIONS, SOCIAL — all integer) | Removed from Facebook API v25 | Drop column. This was a nested object — any flattened columns like `bid_info__CLICKS`, `bid_info__ACTIONS`, etc. should also be removed. |
| `bid_amount` | `integer` | Moved to AdSet level only in API v25; no longer readable on individual Ads | Drop from ads table. **Note**: `bid_amount` is still available on the `adsets` stream — update any queries to source it from there instead. |
| `conversion_specs` | `array` of objects (action.type, conversion_id — both arrays of strings) | Not readable in API v25 | Drop column. Any flattened sub-columns (`conversion_specs__action_type`, `conversion_specs__conversion_id`) should also be removed. |

### Ad Accounts Stream (`adaccounts`)

| Field | Type | Reason | Downstream Impact |
|-------|------|--------|-------------------|
| `salesforce_invoice_group_id` | `string` | Not in Facebook API v25 documentation | Drop column. Was likely null for most accounts. |

### Creatives Stream (`creatives`)

| Field | Type | Reason | Downstream Impact |
|-------|------|--------|-------------------|
| `effective_instagram_story_id` | `string` | Removed in Facebook API v25 | Drop column. |
| `instagram_story_id` | `string` | Removed in Facebook API v25 | Drop column. |
| `instagram_actor_id` | `string` | Removed in Facebook API v25 (replaced — see RENAMED below) | Drop column. Replaced by `instagram_user_id`. |
| `page_link` | `string` | Removed in Facebook API v25 | Drop column. |
| `page_message` | `string` | Removed in Facebook API v25 | Drop column. |

### Campaigns Stream (`campaigns`)

| Field | Type | Reason | Downstream Impact |
|-------|------|--------|-------------------|
| `daily_budget` (duplicate) | `integer` | Was declared twice in schema; removed the duplicate at line 130. The field still exists (line 105). | **No impact** — the field is still emitted. Only the duplicate schema declaration was cleaned up. |

### Adsets Stream (`adsets`)

| Field | Type | Reason | Downstream Impact |
|-------|------|--------|-------------------|
| `geo_locations` (duplicate) | `object` (countries, location_types) | First of two `geo_locations` declarations removed; the more complete second one (with cities, country_groups, custom_locations, regions, zips, etc.) remains. | **No impact** — the field is still emitted with the same or more sub-fields than before. |

---

## RENAMED Fields

### Creatives Stream (`creatives`)

| Old Field | New Field | Type | Notes |
|-----------|-----------|------|-------|
| `instagram_actor_id` | `instagram_user_id` | `string` | Facebook renamed this in API v22. Same data, different field name. **Update all downstream references.** |

---

## NEW Required Config

| Field | Change | Impact |
|-------|--------|--------|
| `access_token` | Now declared as `required: true` in config schema | Was used but undeclared. HotGlue/orchestrators that rely on `--about` output will now see it listed. No breaking change for existing configs that already provide it. |

---

## BEHAVIORAL Changes (no schema change, but different behavior)

| Change | Before | After | Impact |
|--------|--------|-------|--------|
| **API version** | v21.0 | v25.0 | Different API behavior, field availability, rate limits. Data values may differ slightly between API versions. |
| **Error handling** | 4xx errors silently skipped | 4xx errors raise `FatalAPIError` | Syncs will now **fail** on bad requests instead of silently dropping data. This is safer but means failed syncs need investigation. |
| **Batch error handling** | Non-retryable batch errors skipped (`data = {}`) | Raises `RuntimeError` | Same as above — no more silent data gaps in insights. |
| **Fields serialization** | Python list repr `"['field1', 'field2']"` | Comma-separated `"field1,field2"` | The API was likely ignoring the malformed parameter and returning default fields. After this fix, the API will return **exactly the requested fields**. This may cause previously-null columns to start populating, or previously-populated default-only columns to disappear if they weren't in the columns list. |
| **Incremental sort** | No sort params | `sort=asc`, `order_by=replication_key` | Records now arrive in chronological order. Bookmarks are more reliable. No schema impact. |
| **start_date** | Required (would crash if missing) | Optional (falls back to 37 months ago) | Existing configs with start_date are unaffected. New configs without it will pull max history. |

---

## Streams NOT Changed (schema-safe)

These streams have **no field-level changes** — their schemas are identical before and after:

- `adsets` (no field removals, only duplicate geo_locations cleanup)
- `campaigns` (no field removals, only duplicate daily_budget cleanup)
- `adlabels`
- `adimages`
- `advideos`
- `customaudiences`
- `customconversions`
- `adsinsights_default` (and custom insight reports)

---

## Migration Checklist for Downstream Systems

### Data Warehouse / Target Tables
- [ ] Drop `bid_type` column from `ads` table
- [ ] Drop `bid_info` column (and any flattened sub-columns) from `ads` table
- [ ] Drop `bid_amount` column from `ads` table
- [ ] Drop `conversion_specs` column (and any flattened sub-columns) from `ads` table
- [ ] Drop `salesforce_invoice_group_id` column from `adaccounts` table
- [ ] Drop `effective_instagram_story_id` column from `creatives` table
- [ ] Drop `instagram_story_id` column from `creatives` table
- [ ] Drop `instagram_actor_id` column from `creatives` table
- [ ] Add `instagram_user_id` column to `creatives` table (or rename existing)
- [ ] Drop `page_link` column from `creatives` table
- [ ] Drop `page_message` column from `creatives` table

### BI / Reporting
- [ ] Update any reports that reference `bid_type`, `bid_info`, or `bid_amount` on ads
- [ ] Update any reports that reference `instagram_actor_id` → use `instagram_user_id`
- [ ] Update any reports that reference `page_link` or `page_message` on creatives
- [ ] Verify `bid_amount` queries now source from `adsets` instead of `ads`

### Transformation Scripts (dbt, gluestick, etc.)
- [ ] Update any dbt models that SELECT removed fields
- [ ] Update any dbt tests that assert on removed fields
- [ ] Rename `instagram_actor_id` references to `instagram_user_id`
- [ ] Review any logic that depended on `conversion_specs` for attribution

### HotGlue / Orchestration
- [ ] Verify target connector handles missing columns gracefully (most do)
- [ ] Monitor first sync after upgrade for schema evolution in target
- [ ] Be prepared for sync failures (previously silently skipped errors now fail)
