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

The next continuation began at Seattle window 42 (2025-02-28 through 2025-03-29). Attempt `20260930T041759Z-3de2a8aeda` reached the revised source deadline and saved status `failed`, error type `SourceDeadlineExceeded`, one unresolved full-window gap, and zero rows. This live run confirms the remaining-time check stops a prolonged retry; windows 43–91 were not requested. Complete local capture remains 38 of 180 windows, with unresolved windows 12, 25, 41, and 42. No Snowflake load ran.

The approved bounded RAW loader subsequently inspected all 38 complete local history candidates. Its visible terminal reported 36 new windows loaded and reconciled (windows 3–11, 13–24, and 26–40), 0 ready remaining, and no error. These new windows total 9,544 RAW rows from their validated manifests; together with previously loaded windows 1–2 (167 and 185 rows), the 38 history attempts account for 9,896 loaded RAW rows. The loader compared each COPY result and attempt-filtered RAW count with its local manifest before appending a complete receipt. This is loader-reported evidence; an independent aggregate receipt query has not yet been run. The earlier 15-row one-day sample is a separate overlapping attempt and is not included in 9,896. The four unresolved history windows remain 12, 25, 41, and 42. Warehouse credits and stage storage charges have not been measured.

The next 50-window source continuation from window 43 captured windows 43–71 before stopping at San Francisco window 72. All 29 completed manifests matched count-before, returned features, count-after, and local JSONL lines, with zero gaps; they contain 22,467 rows in total. Windows 43–60 finish the Seattle plan, and 61–71 begin San Francisco. Window 72 (2022-08-29 through 2022-09-29), attempt `20260930T043552Z-b9a86fa447`, reached the source deadline and saved a failed manifest with one unresolved gap and zero rows. Windows 73–92 were not requested. Sixty-seven of 180 planned windows now have complete local captures; unresolved windows are 12, 25, 41, 42, and 72. The 29 new captures are local only and have not been loaded into Snowflake.

The next continuation began at San Francisco window 73 (2022-09-29 through 2022-10-29). Attempt `20260930T044001Z-39526ae409` reached the three-minute source deadline and saved a failed manifest with one unresolved full-window gap and zero rows. No additional window was completed; windows 74–122 were not requested. Complete local capture remains 67 of 180, with unresolved windows 12, 25, 41, 42, 72, and 73. No Snowflake load ran.

A diagnostic USGS FDSN count request for the first UTC day inside San Francisco window 73 (2022-09-29 through 2022-09-30, same public site center and 250 km radius) returned `51` within the 20-second client limit. This is only a one-day count, not a capture or reconciliation of the month. It suggests that smaller bounded requests may be worth testing for this gap; the month remains unresolved.

A seven-day count for 2022-09-29 through 2022-10-06 with the extractor's additional `includedeleted=true` and `orderby=time-asc` options timed out at the 20-second client limit (`curl` exit 28). Because both range and options changed from the successful one-day diagnostic, this does not yet isolate which caused the slowdown. No features were captured and window 73 remains unresolved.

The one-day diagnostic with those extra options initially returned HTTP 400 because the manual `curl` command omitted `format=geojson`; USGS explained that `includedeleted` requires GeoJSON or CSV format. The extractor already includes `format=geojson`, so this was a diagnostic-command error, not an extractor bug. Repeating the one-day count with the complete extractor parameter set returned `{"count":51,"maxAllowed":20000}` promptly. The seven-day timeout above also omitted `format=geojson`, so it should not be used to infer a range-size threshold; an exact-parameter seven-day test is still needed.

The exact-parameter seven-day count for 2022-09-29 through 2022-10-06 returned `{"count":341,"maxAllowed":20000}` within the 20-second client limit. This supports trying week-sized audited child requests for slow monthly windows. It does not reconcile or load any events; window 73 remains unresolved until all child counts and feature responses match.

A live retry of San Francisco window 73 with `--source-days 7`, attempt `20260930T045509Z-dced076363`, reached the three-minute source deadline while requesting counts. It saved status `failed`, one unresolved full-month gap, and zero rows. The current manifest does not identify which week was active when the deadline expired; preserving per-child progress in the audit is the next fix. The successful standalone seven-day count therefore did not establish that the full monthly capture would complete. Window 73 remains unresolved and was not loaded into Snowflake.

After adding incremental child audit, a new week-sliced attempt for window 73, `20260930T050144Z-90ed53db7b`, reconciled its first three children: 341, 369, and 354 rows, with before/returned/after counts matching in each. The fourth child, 2022-10-20 through 2022-10-27, reached the source deadline and is recorded as `w0001.4` with an unresolved gap; the fifth child was not requested. The attempt wrote zero rows because the logical month was incomplete. This identifies the slow slice without claiming coverage of the month. No Snowflake load ran.

An exact-parameter one-day USGS count for 2022-10-20 through 2022-10-21, inside the slow fourth child, returned `{"count":170,"maxAllowed":20000}` promptly. This supports trying one-day source slices for window 73, but it does not establish that the remaining days or the full month will reconcile. The gap remains open.

A one-day-sliced retry of the full window 73, attempt `20260930T051517Z-1ee16d7035`, reconciled 26 daily child requests, representing 1,451 returned features in its audit. Child `w0001.27` (2022-10-25 through 2022-10-26) reached the three-minute monthly source deadline; children 28–30 were not requested. The attempt is `failed` with one precise unresolved child gap and zero JSONL rows because the whole logical month did not complete. The repeated full HTTP read-timeout retries consumed the remaining monthly budget before the extractor could split this slow day. Window 73 remains unresolved and was not loaded into Snowflake.

The next source continuation started at window 74 and completed all 50 requested windows, 74–123, on 2026-09-30. These comprise San Francisco windows 74–120 and Anchorage windows 121–123. Their 50 manifests are `complete`, with no coverage gaps; for each audited child, USGS count before, returned features, and count after match. Manifest row totals also match local JSONL line counts. The batch contains 83,844 local raw rows. Overall, 117 of 180 planned monthly site windows have complete local captures. Windows 12, 25, 41, 42, 72, and 73 remain unresolved; the other 57 windows have not yet been captured. No Snowflake call was made for this continuation, and its 50 attempts remain local only.

The next source continuation completed Anchorage windows 124–173 on 2026-09-30. All 50 manifests are `complete`, with zero coverage gaps. For every audited child, USGS count before, returned features, and count after match; manifest totals also match local JSONL line counts. These captures contain 89,565 local raw rows. Overall, 167 of 180 planned monthly site windows have complete local captures. The six earlier gaps remain unresolved, and windows 174–180 have not yet been captured. No Snowflake call was made for this continuation; these 50 attempts remain local only.

The final first-pass source continuation completed Anchorage windows 174–180 on 2026-09-30. All seven manifests are `complete`, with zero coverage gaps. Each audited child has matching USGS count before, returned features, and count after; the 8,574 manifest rows match local JSONL line counts. All 180 planned monthly site windows have now been attempted: 174 have complete local captures, while windows 12, 25, 41, 42, 72, and 73 remain unresolved. These seven new attempts are local only; no Snowflake call was made.

A one-day-sliced retry of Seattle window 12, attempt `20260930T055443Z-18c52e19c2`, reconciled its first ten daily children. The eleventh child, 2022-09-08 through 2022-09-09 UTC, exceeded the three-minute source deadline and is recorded as an unresolved child gap. The attempt is `failed` and wrote zero JSONL rows because the full logical month did not reconcile. Window 12 remains unresolved and was not loaded into Snowflake.

A one-day-sliced retry of Seattle window 25, attempt `20260930T060246Z-ad1808472c`, completed all 30 daily children. Their USGS count-before, returned-feature, and count-after values match individually; the 412 returned features match the local JSONL line count, with zero coverage gaps. This resolves the local source-capture gap for window 25. Overall, 175 of 180 planned windows now have complete local captures; windows 12, 41, 42, 72, and 73 remain unresolved. This attempt has not been loaded into Snowflake.
