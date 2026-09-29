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

On 2026-09-29, the planned Seattle window from 2021-09-29 through 2022-09-29 failed during the USGS count request with a read timeout. Attempt `20260929T160547Z-b60d35bf44` has status `failed`, one structured unresolved coverage gap for the full requested window, and no `events.jsonl`. It was not staged or loaded into Snowflake. The full year is not yet reconciled; the failed attempt remains in the audit history.

A smaller Seattle request from 2021-09-29 through 2021-10-29 succeeded as attempt `20260929T161003Z-5d0e466a47`: count before 167, features returned 167, count after 167, and 167 local JSONL lines. Its manifest is `complete` with no coverage gaps. This covers only the one-month slice; it does not resolve the rest of the failed one-year window. The Python loader subsequently reported `Loaded and reconciled RAW rows: 167` for this attempt after its COPY and attempt-filtered RAW counts matched and the receipt insert completed without an error. An independent read of this receipt has not yet been performed.

The local history planner was subsequently changed to 60 month-sized windows per site, retaining the same five-year cutoff and public sites. Its first Seattle window matches this successful capture. The remaining windows still need extraction and count reconciliation; the failed year-long attempt remains in the audit history.

Seattle monthly window 2, 2021-10-29 through 2021-11-29, completed as attempt `20260929T162551Z-742a6474a5`: USGS count before 185, returned features 185, count after 185, and 185 local JSONL lines. The manifest reports one reconciled window and no coverage gaps. The loader later reported `Loaded and reconciled RAW rows: 185` for this attempt. An independent receipt query has not yet been run.

A separate local capture, `20260929T162532Z-5cac86e7be`, has the same logical batch ID and also reconciled 185 source rows; it was not loaded. A second invocation of the loader for the already-loaded `742a6474a5` attempt stopped at its immutable-receipt guard before PUT or COPY. These observations do not establish full repeat-run idempotency of the downstream warehouse models.

Seattle monthly window 3, 2021-11-29 through 2021-12-29, completed as local attempt `20260929T163325Z-673ecac05f`: USGS count before 155, returned features 155, count after 155, and 155 JSONL lines. The manifest shows one reconciled window and no coverage gaps. This attempt has not been staged or loaded into Snowflake.

The bounded resume runner's first live run for Seattle monthly window 4, 2021-12-29 through 2022-01-29, initially failed because the restricted execution environment could not resolve the USGS hostname. Attempt `20260929T175827Z-70cdef1dcf` records status `failed`, one coverage gap, and zero raw rows. A retry with network access succeeded as a separate attempt, `20260929T175854Z-cb9927c2b1`: count before 193, returned features 193, count after 193, and 193 local JSONL lines. Its manifest is `complete` with zero coverage gaps. Window 4 has not been staged or loaded into Snowflake.

The next bounded run captured Seattle windows 5–7 in one invocation on 2026-09-29. Window 5 (`20260929T180021Z-3d2b3c35a7`) reconciled 267 before/returned/after and 267 JSONL lines; window 6 (`20260929T180023Z-c0b0727a50`) reconciled 203; window 7 (`20260929T180024Z-566cd3c453`) reconciled 248. Each manifest is `complete` with zero coverage gaps. These are local captures only and have not been staged or loaded into Snowflake. Seven of 180 planned monthly site windows now have complete local captures.
