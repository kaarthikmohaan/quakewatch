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

`manifest.json` records the requested site and time range, query parameters, per-window counts before and after retrieval, returned and written row counts, and final status. Local raw output is ignored by Git. The 15-row day and 167-row month around Seattle have been loaded into the Snowflake RAW table; the local files remain as capture evidence.

## Planned warehouse grains

See [design.md](design.md) for the full model. The planned raw grain is one source feature returned by one query window in one attempt. The planned revision fact grain is one distinct canonical event revision. The current-event view will select the latest non-stale revision and hide a latest tombstone.

## Phase 1 raw tables

The [raw-table SQL](../sql/phase1_raw_tables.sql) created two tables in `QUAKEWATCH.RAW` on 2026-09-29. `DESCRIBE TABLE` verified their columns and types. Two Seattle source attempts, with 15 and 167 rows, have since been loaded:

| Table | Grain and important fields |
|---|---|
| `BATCH_ATTEMPT` | One append-only receipt per extract/load attempt, including failures. `LOGICAL_BATCH_ID` groups retries; `ATTEMPT_ID` identifies this execution. It keeps requested bounds, query parameters, window audit, coverage gaps, source/written/loaded counts, statuses, copy results, and the complete manifest. An update sweep can have no `SITE_KEY`. |
| `RAW_EVENT_RECORDS` | One returned GeoJSON feature per attempt and query window. `PAYLOAD VARIANT` retains the complete `source_feature`. Attempt/window IDs, fetch time, payload hash, parser version, staged file name and file row number identify where it came from. |

The pair `(STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER)` identifies a row in a staged file. The loader must use an attempt-specific stage path so this pair stays stable. It is not a global event ID and it does not deduplicate overlapping windows or retry attempts. Phase 1 load logic must reconcile these rows with the attempt manifest; Phase 2 will deduplicate logical event revisions.
