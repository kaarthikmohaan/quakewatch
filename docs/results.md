# Results

## First live source capture

| Measure | Observed value |
|---|---|
| Site | Seattle public example point, 250 km radius |
| Requested range | 2026-09-28 00:00 UTC through 2026-09-29 00:00 UTC |
| Count before fetch | 15 |
| Features returned | 15 |
| Count after fetch | 15 |
| Raw JSON Lines written | 15 |
| Window result | Reconciled |
| Snowflake RAW rows loaded | 15, reported by the first loader run |

This is one source-capture observation, not a completeness guarantee or a performance claim. The local manifest and source rows are under ignored `data/raw/` and are not published to GitHub.

## First RAW load

On 2026-09-29, the Python loader ran for attempt `20260929T075452Z-26375840ea`. Its manifest and local JSONL each contained 15 rows. The visible terminal reported `Loaded and reconciled RAW rows: 15` after the COPY result and attempt-filtered RAW count both matched 15 and the append-only batch receipt insert returned without an error. An independent read through the Snowflake Python Connector then returned `(receipt_count=1, load_status='complete', loaded_rows=15, raw_rows=15)` for this attempt. Warehouse credits and stage storage charges have not been measured.

## Not measured yet

- Repeat-batch idempotency and revision/tombstone behavior
- Snowflake fetch-to-curated latency, rejects, and pending batches
- FDSN update-sweep coverage gaps
- Warehouse credit usage
- User task completion time or usefulness

## First history-window attempt

On 2026-09-29, the planned Seattle window from 2021-09-29 through 2022-09-29 failed during the USGS count request with a read timeout. Attempt `20260929T160547Z-b60d35bf44` has status `failed`, one structured unresolved coverage gap for the full requested window, and no `events.jsonl`. It was not staged or loaded into Snowflake. This window remains uncovered; a smaller bounded request is the next diagnostic step.
