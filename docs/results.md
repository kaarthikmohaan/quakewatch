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

A read-only Snowflake receipt check on 2026-09-29 compared these seven local candidates with `BATCH_ATTEMPT` receipts and attempt-filtered `RAW_EVENT_RECORDS` counts. Windows 1 and 2 were `loaded` with matching local, receipt, and RAW row counts. Windows 3–7 were `ready`, with no receipt and no RAW rows. Counts: loaded 2, ready 5, investigate 0. The check ran no PUT or COPY. Warehouse credits from this check were not measured.

A requested 50-window USGS capture run stopped at Seattle window 12 on 2026-09-29. Windows 8–11 completed with reconciled local counts of 263, 224, 234, and 360 respectively, each with zero coverage gaps. Window 12 (2022-08-29 through 2022-09-29) timed out after bounded HTTP retries. Attempt `20260929T181215Z-6db1c7476f` records one unresolved gap and zero rows. A separate retry, `20260929T181444Z-57b624f069`, timed out the same way and also retains one gap and zero rows. The runner stopped at the gap; windows 13–57 were not requested. Eleven of 180 planned monthly site windows have complete local captures, but window 12 is not covered. None of windows 8–11 has been loaded into Snowflake.

A third window-12 attempt with timeout splitting, `20260929T182006Z-2b8d22d8e1`, also failed. Its audit records splits at `w0001`, `w0001.a`, and `w0001.a.b`; `w0001.a.a` reconciled, but `w0001.a.b.a` still timed out at the configured depth limit. The attempt retained one unresolved leaf gap and wrote zero rows, so no partial month is being treated as complete. The explicit start-window option can continue later months while window 12 remains outstanding.

An explicit continuation from Seattle window 13 captured windows 13–15 on 2026-09-30. Attempts `20260930T024713Z-a839f4d513`, `20260930T024715Z-49975e5095`, and `20260930T024716Z-5d777c6173` reconciled 259, 244, and 204 rows respectively; each count-before, returned-feature count, count-after, and JSONL line count matched with zero gaps. Fourteen of 180 planned windows now have complete local captures. Window 12 remains unresolved, and windows 13–15 have not been loaded into Snowflake.

The next 50-window continuation from window 16 captured windows 16–24 before a prolonged source timeout at window 25. Their reconciled local row counts were 162, 232, 213, 216, 240, 212, 284, 367, and 436, totaling 2,362 rows; each count-before, returned-feature count, count-after, and JSONL line count matched with zero gaps. Attempt `20260930T025128Z-390c1c6b51` for window 25 (2023-09-29 through 2023-10-29) was interrupted after prolonged read-timeout retries. Its manifest is marked `failed` with an explicit unresolved full-window gap and zero rows; partial work is not counted. Windows 26–65 were not requested. Twenty-three of 180 planned windows now have complete local captures, with unresolved windows 12 and 25. The new captures have not been loaded into Snowflake.

The continuation from window 26 captured windows 26–40 before a prolonged timeout at window 41. Their reconciled local row counts were 262, 202, 184, 210, 258, 299, 315, 384, 327, 335, 502, 368, 217, 233, and 232: 4,328 rows total. Each complete attempt matched count-before, returned features, count-after, and JSONL lines, with no gaps. Window 41 (2025-01-29 through 2025-02-28), attempt `20260930T032225Z-a2077ba962`, was interrupted after the initial signal-based deadline failed to stop its network retries; it is `failed` with one full-window gap and zero rows. Windows 42–75 were not requested. The deadline implementation was then changed to check remaining time before every HTTP request and retry wait; that revised mechanism has passed offline tests but has not yet been observed in a live timeout. Thirty-eight of 180 planned windows have complete local captures; windows 12, 25, and 41 remain unresolved. These new captures have not been loaded into Snowflake.
