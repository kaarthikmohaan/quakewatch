# Data dictionary

## Current local extract

The extractor writes one JSON object per line to `events.jsonl`. Each line contains the complete USGS GeoJSON feature under `source_feature` and capture metadata under `metadata`.

| Field | Meaning |
|---|---|
| `source_feature` | Full source GeoJSON feature, preserved without narrowing its properties |
| `metadata.logical_batch_id` | Stable identifier for the requested site and time range |
| `metadata.attempt_id` | Unique identifier for this execution, including retries |
| `metadata.window_id` | Query window that returned this observation; recursive splits get child IDs |
| `metadata.fetched_at` | UTC time the local batch captured the feature |
| `metadata.payload_hash` | SHA-256 of canonicalized source-feature JSON |
| `metadata.parser_version` | Version of the local raw-record envelope; currently `1` |

`manifest.json` records the requested site and time range, query parameters, per-window counts before and after retrieval, returned and written row counts, and final status. Local raw output is ignored by Git. The 15-row Seattle sample and 177 complete planned history windows have been loaded into the Snowflake RAW table; three planned history windows remain source gaps. See [observed results](results.md) for verified counts.

## Planned warehouse grains

See [design.md](design.md) for the full model. The planned raw grain is one source feature returned by one query window in one attempt. The planned revision fact grain is one distinct canonical event revision. The current-event view will select the latest non-stale revision and hide a latest tombstone.

## Phase 1 raw tables

The [raw-table SQL](../sql/phase1_raw_tables.sql) created two tables in `QUAKEWATCH.RAW` on 2026-09-29. `DESCRIBE TABLE` verified their columns and types. The subsequent read-only receipt check confirmed 177 complete history attempts loaded with matching RAW counts:

| Table | Grain and important fields |
|---|---|
| `BATCH_ATTEMPT` | One append-only receipt per extract/load attempt, including failures. `LOGICAL_BATCH_ID` groups retries; `ATTEMPT_ID` identifies this execution. It keeps requested bounds, query parameters, window audit, coverage gaps, source/written/loaded counts, statuses, copy results, and the complete manifest. An update sweep can have no `SITE_KEY`. |
| `RAW_EVENT_RECORDS` | One returned GeoJSON feature per attempt and query window. `PAYLOAD VARIANT` retains the complete `source_feature`. Attempt/window IDs, fetch time, payload hash, parser version, staged file name and file row number identify where it came from. |

The pair `(STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER)` identifies a row in a staged file. The loader must use an attempt-specific stage path so this pair stays stable. It is not a global event ID and it does not deduplicate overlapping windows or retry attempts. Phase 1 load logic must reconcile these rows with the attempt manifest; Phase 2 will deduplicate logical event revisions.

## Phase 2 typed staging contract

`STG_EVENT_REVISION` has one row per RAW source observation, before revision deduplication. It reads `RAW_EVENT_RECORDS.PAYLOAD` without modifying that `VARIANT`. The source attempt ID, window ID, fetch time, payload hash, and staged file-row key remain attached so a rejected projection can be traced back to its original feature.

| Typed field | GeoJSON source | Rule |
|---|---|---|
| `source_event_id` | `id` | Required non-empty string; preserve exactly as supplied |
| `origin_time` | `properties.time` | Required epoch milliseconds, converted to UTC |
| `source_updated_at` | `properties.updated` | Required epoch milliseconds, converted to UTC |
| `source_status` | `properties.status` | Required non-empty string; `deleted` remains a tombstone candidate |
| `associated_ids` | `properties.ids` | Preserve the source list for later alias resolution; absence is allowed |
| `magnitude`, `magnitude_type`, `place` | `properties.mag`, `magType`, `place` | Nullable typed attributes; never infer a missing magnitude |
| `longitude`, `latitude`, `depth_km` | `geometry.coordinates` | Validate a Point's longitude/latitude for active records; allow nullable geometry on a deleted tombstone |

An invalid required ID, clock, status, or active-record location goes to rejects with a reason and its RAW source key. Optional fields and newly added source fields remain in the preserved `VARIANT`; they do not silently change this typed contract. This staging step does not choose a canonical ID or a current revision. Those decisions belong to the revision fact and current view after alias and tombstone rules are applied.

The local [staging DDL](../sql/phase2_staging_table.sql) defines this grain in `QUAKEWATCH.CURATED.STG_EVENT_REVISION`. It carries the staged file-row key, attempt/window IDs, fetch time, payload hash, both RAW and staging parser versions, the typed fields above, `REJECT_REASON`, and projection time. The table has not been created in Snowflake yet; wiring the parser into the Snowpark procedure remains a later implementation step. `CREATE TABLE IF NOT EXISTS` does not verify an existing table's shape, so inspect it before applying this DDL.

The local [projection function](../src/quakewatch/staging.py) implements the first row-level parser contract for the eventual Snowpark procedure. It converts integer epoch milliseconds to UTC, checks required ID/time/status and active Point coordinates, and returns one stable `reject_reason` for an invalid row. A deleted feature may have no geometry. Nullable magnitude, magnitude type, place, and depth stay nullable; malformed non-null values are rejected rather than silently cast. The USGS comma-delimited `properties.ids` becomes a list for later alias work. This function does not modify RAW, load Snowflake, resolve aliases, or choose a current revision.
