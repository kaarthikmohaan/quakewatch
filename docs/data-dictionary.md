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

`manifest.json` records the requested site and time range, query parameters, per-window counts before and after retrieval, returned and written row counts, and final status. Raw output is currently local and ignored by Git. No Snowflake table has been created yet.

## Planned warehouse grains

See [design.md](design.md) for the full model. The planned raw grain is one source feature returned by one query window in one attempt. The planned revision fact grain is one distinct canonical event revision. The current-event view will select the latest non-stale revision and hide a latest tombstone.
