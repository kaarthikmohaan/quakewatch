# Results evidence log

The dated record behind the [results summary](../results.md), newest first.
Each entry keeps its query IDs, counts, and limits as originally recorded.

**Conventions used throughout:**

- Unless an entry states a figure, Snowflake warehouse credits, cloud-services
  usage, and stage or storage charges were **not measured** for that step.
- A window is **reconciled** when the USGS count before the fetch, the returned
  features, the count after, and the saved JSONL lines all match. A
  **complete** capture has manifest status `complete` and zero coverage gaps.
- A **local capture** was not loaded into Snowflake when it was recorded; load
  runs are listed separately.
- Counts are source observations, not unique earthquakes, and are not proof of
  complete USGS coverage. History windows 12, 42, and 73 remain source gaps, and
  no update-sweep watermark has been committed.

## Parser version 2 release (2026-10-02)

`make release-parser-v2 EXECUTE=1` ([runner](../../scripts/pipeline/release_parser_v2.py))
ran under `QUAKEWATCH_ROLE` on `QUAKEWATCH_WH`, with the passphrase entered at
the terminal prompt. Its pre-checks matched the offline replay: 216,391 staging
rows, 485 `invalid_origin_time` rejects whose RAW payloads were all USGS stub
features, no valid row at `[0, 0]`, and all fact rows at version 1. In one
transaction it then relabelled exactly 485 rejects as `source_stub_record` and
marked 216,391 staging rows and 215,877 fact rows as parser version 2, rechecked
the counts, and committed. It then uploaded the version 2 procedure bundle
(SHA-256 `2c97f4fac277ac3bc0fd7d16d4482447f86eba6fad5532d4e191416700053e73`),
replaced `PROCESS_LOADED_ATTEMPT`, and created `QUAKEWATCH.RAW.UPDATE_WATERMARK`.
The final staging state was 215,906 valid rows and 485 `source_stub_record`
rejects, all at version 2. Query IDs were not captured, and the run's
warehouse credits were not measured.

## Live end-to-end Seattle demo (2026-10-02)

A new bounded capture for the public Seattle point and 2026-09-28 UTC first
failed at local DNS resolution and produced no loadable batch. The retry saved
complete attempt `20261002T045249Z-ee3a351be3` under Git-ignored `data/raw/`:
one reconciled window of 15 rows (15 count-before, 15 returned, 15
count-after), with the manifest and JSONL both holding 15 rows.

**Load and process.** `COPY INTO` and attempt-filtered RAW each reported 15
rows. The health row moved from `PENDING_PROCESS` (15 loaded and RAW rows) to
`RECONCILED` (15 loaded, RAW, staged, and processed; zero rejects). The
procedure returned `status=complete`, 15 processed, zero rejected, and 15
revision rows merged; a MERGE count can include updates to known revisions, so
it is not a count of new earthquakes. Process attempt ID:
`530ff2a08e23448ca2d0d931a87bd264`.

**Warehouse checks.** The Seattle current-event query returned 15 modeled
events within the public radius, magnitudes 0.66 to 2.56. The read-only quality
check found **179 reconciled receipts** and **216,391** loaded, RAW, staged, and
processed observations (177 history attempts plus two overlapping 15-row
Seattle samples), 485 rejects, zero batch or window anomalies, and zero
duplicate revision or bridge-key groups. The ten-case aggregate query matched
the earlier saved snapshot.

**Cortex: two briefs rejected.** One `llama3.1-8b` call (query ID
`01c7742a-0002-b28e-000e-fef20003c0aa`, 141 prompt and 76 completion tokens)
summarised the Seattle-day facts: 15 modeled events, nearest event
`uw714111042` 42.1 km from the site, magnitude 1.23, `reviewed`, 78.3 hours
old. The sentence measured the distance from the event ID rather than the site,
so local validation rejected it and the SQL facts remained the output. A later
walkthrough repeated the call (query ID `01c77438-0002-b28e-000e-fef20003c0ca`,
record age 78.6 hours) with the same error and rejection. These are the twelfth
and thirteenth completed Cortex calls; their credits are unmeasured.

**Recovery drill.** Two runs of the uniquely named fixture clone drill passed.
Each cloned the five-row fixture fact, changed one clone magnitude from 1.1 to
1001.1, confirmed the source still held 1.1, read 1.1 from before the change
with Time Travel, and dropped the clone. Only the isolated fixture database was
touched.

| Run | Clone query ID | MERGE query ID | DROP query ID |
|---|---|---|---|
| First | `01c7742b-0002-b423-000e-fef200044012` | `01c7742b-0002-b2f7-000e-fef20004008a` | `01c7742b-0002-b3cf-000e-fef200041072` |
| Second | `01c77439-0002-b28e-000e-fef20003c0d6` | `01c77439-0002-b2f7-000e-fef2000400aa` | `01c77439-0002-b2f7-000e-fef2000400b2` |

Local test discovery passed all 303 tests. The demo did not rerun the five-year
backfill, fill the source gaps, advance the watermark, measure its warehouse
credits, or run a target-user interview. Step-by-step detail is in the
[live demo walkthrough](../runbook.md).

## Phase 4 ten-case Cortex aggregate snapshot

I ran the read-only aggregate query on 2026-10-01 under `QUAKEWATCH_ROLE` and
`QUAKEWATCH_WH`. It saved ten public-site, fixed-window rows to Git-ignored
`data/cortex/phase4_aggregates.json`, each with a hash of its input. Query ID:
`01c77065-0002-b136-000e-fef20003852e`; reviewed SQL SHA-256:
`9b2110deeb6dfe241b0e6f1b5f2c809d9b6331988fa02ee7f64c6814492c7743`.

| Public site | 2022 | 2024 | 2026 to Sep 29 UTC |
|---|---:|---:|---:|
| Anchorage | 22,056 | 21,711 | 10,685 |
| Seattle | 2,651 | 3,514 | 2,469 |
| San Francisco | 15,975 | 18,859 | 16,183 |

The tenth case, Seattle 2026-09-28 UTC, had 15 modeled events. Every case uses
the one configured 250 km radius and has a nonzero count and a nearest event
with magnitude, source status, and record age. Neither the script nor the file
contains site coordinates. The query may have resumed warehouse compute; no
Cortex call was made in this step.

## Phase 4 nine-case Cortex evaluation

On 2026-10-01 the bounded evaluator ran for the nine annual public-site cases;
the Seattle day was excluded because its earlier `llama3.1-8b` result had used
its one retry. It used `claude-haiku-4-5` under `QUAKEWATCH_ROLE`, issued
exactly nine `AI_COMPLETE` calls, and saved model, generation time,
input/prompt hashes, query IDs, token usage, output, and validation to
Git-ignored `data/cortex/phase4_briefs.json`. A second invocation returned
`status=cached`, `new_calls=0`, so no duplicate paid calls were made.

All nine passed the strict local screen and human review of every stated UTC
window, modeled count, 250 km radius, nearest event ID and distance **from the
site**, magnitude, source status, and age at SQL check time. None made a
hazard, action, or complete-coverage claim, and the cache marks each review as
passed. This shows factual agreement for these nine point-in-time aggregates
only, not complete coverage or that a target user prefers the text.

**Tokens and credits.** The nine calls used 1,845 prompt and 926 completion
tokens. At the published `AI_COMPLETE` rates for this model (0.60 AI credits per
million input tokens, 3.00 per million output), that is about **0.003885 AI
credits**, which the metering query below confirmed. Warehouse credits for these
calls are unmeasured.

I compared the Seattle 2024 SQL row side by side with its brief and found the
brief easier to scan. That is my preference on one example, supporting
continued optional use; it is not a target-analyst interview or a measured
task-time improvement.

**Metering.** At 2026-10-01 13:27:00 UTC the read-only query on
`SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY` (query ID
`01c77087-0002-b1e7-000e-fef200036b0a`) returned all 11 expected query IDs as
completed, totaling **0.003948756 reported AI credits**: **0.003885000** for
the nine `claude-haiku-4-5` briefs and **0.000063756** for the two
`llama3.1-8b` briefs. The trial-account calls that were refused generated no
brief and are not among the 11. This view does not isolate warehouse credits
for the aggregate query, the Cortex calls, or the metering query itself, which
may have used XS compute.

## Phase 4 Cortex trial attempt

Each trial used the public Seattle 2026-09-28 UTC sample, counted modeled
events within the site radius, selected the nearest event, and made at most one
`AI_COMPLETE('llama3.1-8b', ...)` call capped at 120 output tokens. Every SQL
check found 15 modeled events and nearest event `uw714111042`, 42.1 km **from
the Seattle site**, magnitude 1.23, status `reviewed`.

| Attempt | Outcome | Cortex query ID and tokens | SQL count and nearest query IDs | Record age |
|---|---|---|---|---|
| 1 | Refused by Snowflake: `399258 (0A000): AI function _COMPLETE_WITH_PROMPT_HISTORY_LLM is not available for trial accounts` | None | Not recorded | Not recorded |
| 2 (visible terminal) | Returned `cortex_unavailable_for_trial_account`, same error `399258` | None | `01c76fc5-0002-afd6-000e-fef200033a4e`, `01c76fc5-0002-b113-000e-fef200035d76` | 59.6 hours |
| 3 (after a payment method was confirmed) | **Rejected:** said **“15 km Radius”**, treating the event count as a radius, and stopped before the record age | `01c76fcf-0002-afd6-000e-fef200033b12`; 140 prompt, 120 completion | `01c76fcf-0002-b1e7-000e-fef20003693a`, `01c76fcf-0002-b136-000e-fef20003837e` | 59.8 hours |
| 4 (the one allowed retry) | **Rejected in human review:** passed the automatic checks but said "42.1 km away from uw714111042," anchoring the distance to the event's own ID | `01c76fd2-0002-b113-000e-fef200035e4e`; 141 prompt, 82 completion | `01c76fd2-0002-afd6-000e-fef200033b1e`, `01c76fd2-0002-b136-000e-fef200038386` | 59.8 hours |

After the first two refusals no Cortex summary existed; Snowflake's
trial-account documentation says AI features stay disabled until a credit card
is added, and I verified the payment method in Snowsight before authorizing a
paid attempt. No account billing setting was changed here. These early trial
calls used the local administrator profile; the saved trial runner was later
changed to run as `QUAKEWATCH_ROLE`, matching the nine-case evaluator.

After attempt 3, a tighter one-sentence prompt and local validation were added
to reject missing facts, unsupported radius-size claims, hazard language, and
truncated endings; that revision was not sent to Cortex. After attempt 4 the
validator also rejects distance anchored to an event ID. The 260 tokens from
attempt 3 were the first usage evidence; the later metering query measured the
AI credits for attempts 3 and 4. The one-retry limit for this aggregate has been
reached, the SQL facts remain the deterministic fallback, and no usefulness
claim is made from these examples.

## Phase 4 exit review

I accepted the Phase 4 optional-demo exit on 2026-10-01. The sandbox clone and
Time Travel drill passed and was cleaned up, and a read-only metering snapshot
recorded actual shared warehouse-hour credits with latency and attribution
limits. Cortex was left optional and not run at that point. The acceptance does
not close the three USGS history gaps, the incomplete update sweep, the missed
Phase 3 latency target, or the target-user interview.

## Phase 4 sandbox recovery preflight

The read-only preflight on 2026-10-01 passed under `QUAKEWATCH_ROLE` with
`QUAKEWATCH_WH` (final query ID `01c76f7e-0002-b136-000e-fef2000380fa`). The
isolated fixture `QUAKEWATCH_PHASE2_FIXTURE.CURATED.FACT_EVENT_REVISION` had
five exact rows, five metadata rows, one day of Time Travel retention, and zero
duplicate revision-key groups, and the proposed clone name
`QUAKEWATCH_PHASE2_FIXTURE.CURATED.QW_PHASE4_REVISION_DEMO` was absent. It read
no main `QUAKEWATCH` fact data, changed no table, and on its own does not show
that clone or Time Travel recovery succeeds.

## Phase 4 clone isolation and Time Travel drill

The live drill on 2026-10-01 returned `status=pass`. It created only the clone
`QUAKEWATCH_PHASE2_FIXTURE.CURATED.QW_PHASE4_REVISION_DEMO` of the five-row
fixture revision fact (query ID `01c76f83-0002-b136-000e-fef20003810a`). A
deliberate `MERGE` (query ID `01c76f83-0002-afd6-000e-fef20003390e`) changed
one clone revision for `qw-old-origin-001` from magnitude 1.1 to 1001.1. The
source still had five rows and magnitude 1.1 for that revision key; the clone
had five rows and 1001.1. A `BEFORE (STATEMENT => ...)` read of the clone
returned five rows and the original 1.1, with a pre-merge magnitude range of
1.08–1.3. This shows clone isolation and statement-ID Time Travel for this
sandbox case; the one-day retention limits how long the read can be repeated.

The guarded cleanup on 2026-10-01 returned `status=pass`: it dropped only the
demo clone (query ID `01c76f8f-0002-b113-000e-fef200035cf2`), confirmed it was
gone from fixture metadata, and found the fixture source still had five rows.
No main `QUAKEWATCH` fact table changed. Clone divergence and history storage
were not measured, no dollar cost is claimed, and the hourly snapshot below
cannot isolate the drill's cost.

## Phase 4 warehouse metering snapshot

The read-only Account Usage query on 2026-10-01 at 09:56:08 UTC (query ID
`01c76fb4-0002-b136-000e-fef20003822e`) returned these rows for the shared
`QUAKEWATCH_WH` warehouse:

| UTC warehouse hour | Compute credits | Cloud-services credits | Reported credits |
|---|---:|---:|---:|
| 08:00–09:00 | 0.088875 | 0.004816942 | 0.093691942 |
| 09:00–10:00 | 0.0705 | 0.000996943 | 0.071496943 |

The second hour was still in progress, and Account Usage may lag. The rows
cover all activity on the warehouse in those hours, not only the clone demo,
so they are actual warehouse-hour figures, **not** a per-drill bill or a
dollar amount. Clone storage and account-level billing adjustments were not
measured.

## Phase 3 first-backfill measurement plan (set before live query)

**Plan.** Sample: all complete origin-time attempts in `FACT_BATCH_RUN` whose
requested UTC windows fall within 2021-09-29 through 2026-09-29, across the
three public sites. It includes one overlapping 15-row Seattle pilot, and the
unit is a batch attempt, not an earthquake. Measure the count, the
request/fetch/curation date range, and min/p50/p95/max
`FETCH_TO_CURATED_SECONDS`. Target: at least 30 attempts and p95 no more than
86,400 seconds (24 hours) for this first manually run backfill. Report the last
successful fetch age and newest accepted source-update age separately. This is
a project acceptance target, not a production SLO; the three source gaps and the
incomplete sweep are excluded from the latency sample and stay visible in
coverage reporting. The [reviewed SQL](../../sql/phase3_metrics.sql) and target
were committed before the measurement ran.

**Result (2026-10-01).** 178 attempts, requested-window bounds 2021-09-29
through 2026-09-29 UTC. Fetches began 2026-09-29 07:54:52 UTC; the last
curation was 2026-10-01 07:03:42 UTC. Fetch-to-curated seconds: min 85,670.574,
p50 90,522.7, p95 129,170.4, max 135,791.254. **The 24-hour p95 target was
missed** (35.9 hours observed). Delayed, manually invoked bulk curation drives
this first-backfill figure; it does not describe a scheduled steady-state
service or USGS publication latency. Latency query ID:
`01c76f37-0002-af06-000e-fef200037666`.

**Freshness.** When the separate freshness query ran (query ID
`01c76f37-0002-affb-000e-fef200034592`), the last successful fetch was
2026-09-30 06:19:30 UTC, age 91,918 seconds (25.5 hours), and the newest
accepted source update was 2026-09-30 05:49:06 UTC, age 93,742 seconds (26.0
hours). These ages change over time, and the missing update sweep prevents a
current-catalog freshness claim.

## First GitHub Actions fixture run

The first CI run, for commit `12a167a` on 2026-10-01, failed in the fixture-test
step: GitHub's log showed `FileNotFoundError` for ignored synthetic
`data/procedure/phase2_fixture/attempts/.../manifest.json` files, with all 272
tests discovered and 10 errors. The locked install and Python setup passed. The
generated fixture files existed on the Mac but not in GitHub's fresh checkout,
and a clean local checkout reproduced two further missing-artifact errors for
the ignored fixture procedure ZIP. The workflow now builds the deterministic
fixture ZIP/SQL and synthetic attempts before testing. The
[follow-up CI run](https://github.com/kaarthikmohaan/quakewatch/actions/runs/36831735945)
for commit `bc69dde` completed with `success` on 2026-10-01, and the same
clean-checkout sequence passed all 273 tests locally. CI uses no Snowflake
secrets or live warehouse integration.

## Phase 3 exit review

I accepted the Phase 3 design exit on 2026-10-01: live quality counts, CI, a
dated sample, and the missed predeclared latency target are documented
separately from targets. The acceptance did not close the three USGS history
gaps, the incomplete update sweep, or the then-pending live failed-transform
and retry demonstration.

## Isolated failed-transform and retry drill

**Repeat processing of an already processed batch.** The live fixture drill on
2026-10-01 returned `status=pass` for the loaded `fixture-original-v1` attempt
in `QUAKEWATCH_PHASE2_FIXTURE`. A test-only procedure deliberately raised after
model writes; the coordinator rolled them back and appended one failed
processing audit. The same RAW attempt then went to the normal procedure with no
refetch or RAW reload. Before failure, after failure, and after retry the
snapshot was identical: one RAW row and receipt, six staging rows, five
revision facts, 15 site bridges, six batch facts, three sites, four dates, two
event statuses, one magnitude type, and one current event. The retry's process
attempt was `806e9e2d47c04680a7bfbd4cabd68b6c`, with zero revision and bridge
duplicate groups. This covers a **later processing invocation of a batch that
had already succeeded**, not a first-ever failure; the test-only failure
procedure remains in the fixture database.

**First-ever failure of a newly loaded batch.** The one-shot drill for new
synthetic batch `fixture-first-failure-v1` on 2026-10-01 passed its load and
rollback guards, then raised `first-failure retry did not converge` at its final
guard, after the `PUT`, `COPY`, complete receipt, intentional failure call, and
normal retry call. The read-only
[state diagnostic](../../scripts/evidence/phase2/phase2_first_failure_state.py)
showed one RAW row and receipt, one failed process audit followed by one
complete audit, one staged row and batch fact for the attempt, five total
revision facts, 15 total site bridges, and zero duplicate groups. The RAW hash
`eef7c3945e972555e034cce171c28a1cf044ab1bab8c14c581ca80365f7ef499` matches the
local ignored fixture record. The complete audit reported
`revision_rows_merged=1` because the later fetch updated metadata on an existing
revision; fact and bridge counts did not grow. The guard was wrong to expect
zero MERGE changes, since the writer counts inserts and updates; it now requires
stable logical counts and unique keys. **First-ever transform failure, durable
RAW, append-only failure audit, and retry without refetch are verified for this
one synthetic batch.** Do not rerun the one-shot drill.

## Window 73 checkpoint retry after Phase 3 exit

Attempt `20261001T075447Z-c12460171c` on 2026-10-01 reused the 26 validated
daily checkpoints and their 1,451 features, fetched zero new features, and hit
`SourceDeadlineExceeded` on child `w0001.27` (2022-10-25 through 2022-10-26
UTC). The failed manifest keeps one unresolved gap and no `events.jsonl`; no
load followed. This repeated timeout is an observed source-coverage limit, not a
zero-count window. Identical retries are deferred until a different bounded
request strategy or a source change justifies one.

## First Phase 3 quality deployment attempt

**View deployment.** The first Phase 3 quality run on 2026-10-01 stopped at
preflight because at least one of the three planned view names already existed
in `QUAKEWATCH.CURATED`; it issued no view DDL, reconciliation query, or sample
query. A read-only metadata check then found all three views, with definitions
whose SHA-256 hashes exactly match the reviewed `CREATE VIEW` statements: batch
health `9f37d2ca37e6bc570ff1de9d4b2e423fc4ce094e77384cff850ff68b0f13fca7`,
reject rows `d848cce3d7b1b8aad4ea97ece3e2b3b037a7feb8ac0db74eda660300b9b71c57`,
and window audit `4b79a3d15c11ea589e9fc756ec704a52f885aca89a1cc17945992757639283b1`.

**Reconciliation before processing.** The guarded reuse run executed the three
reconciliation queries and the bounded Seattle sample with `status=pass`, zero
unexpected batch-health rows, and zero unresolved or mismatched rows among
windows with Snowflake receipts. Health showed 177 `PENDING_PROCESS` history
attempts with 216,361 loaded and RAW rows and nothing staged or processed, plus
one `RECONCILED` Seattle attempt with 15 loaded, staged, and processed rows and
zero rejects. The Seattle sample for 2026-09-28 UTC returned 15 events within
the 250 km radius, magnitudes 0.66 to 2.56. The three failed source windows
have no Snowflake receipt.

**History processing.** A five-attempt trial on 2026-10-01 called
`PROCESS_LOADED_ATTEMPT` once per attempt, checking pending RAW and receipt
counts before each call and a reconciled health row after. All five passed:
1,858 + 1,490 + 167 + 1,709 + 1,565 = 6,789 processed rows, zero rejected, no
refetch or reload. That left 172 attempts and 209,572 RAW rows pending, based on
the prior 177-attempt, 216,361-row snapshot. The next run processed all 172 in
one session and ended with `status=pass`, `completed_attempts=172`,
`processed_rows=209572`, and `rejected_rows=485`, stopping on the first mismatch
had there been one. In total, 177 history attempts and 216,361 RAW rows were
processed, 485 of them rejected by typed projection.

**Post-run check.** The read-only check on 2026-10-01 returned `status=pass`:
all 178 receipts were `RECONCILED` (177 history attempts plus the overlapping
15-row Seattle sample), with 216,376 receipt, RAW, staging, and processed rows,
485 rejected rows, zero unexpected batch-health rows, zero loaded-window
anomalies, and zero duplicate revision or bridge-key groups. The reject view
grouped all 485 under `invalid_origin_time`; the
[reject analysis](../results.md#reject-analysis) later traced them to USGS
placeholder records. The original RAW payloads and staged reject rows remain
available for review.

## First Phase 3 uniqueness check

On 2026-10-01 the read-only
[uniqueness runner](../../scripts/checks/phase3_uniqueness.py) ran two
duplicate-group counts against `QUAKEWATCH.CURATED` and returned
`status=pass`, `revision_duplicate_groups=0`, and `bridge_duplicate_groups=0`.
The checks use the full revision key
`(CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH)` and the bridge key with
`SITE_KEY`. This is a point-in-time result, not a guarantee for future loads.

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

This is one source-capture observation, not a completeness guarantee or a
performance claim. The manifest and rows are under ignored `data/raw/`.

## First RAW load

On 2026-09-29 the Python loader ran for attempt `20260929T075452Z-26375840ea`,
whose manifest and JSONL each held 15 rows. The terminal reported
`Loaded and reconciled RAW rows: 15` after the COPY result and attempt-filtered
RAW count both matched 15 and the append-only receipt insert succeeded. An
independent read through the Snowflake Python Connector returned
`(receipt_count=1, load_status='complete', loaded_rows=15, raw_rows=15)`.

## First Phase 2 Snowpark pilot

On 2026-09-30 the bounded pilot uploaded the procedure ZIP, created the Phase 2
curated objects, and called `QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT` once for
the 15-row Seattle attempt. It returned `status=complete`, `loaded_rows=15`,
`processed_rows=15`, `rejected_rows=0`, and `revision_rows_merged=15` (process
attempt `42fc37d34e1545498ad004d8eeb35b72`). Post-call checks found 15 staging
rows, 15 revision facts, 45 event-site bridges, three site rows, one batch fact,
and one processing attempt. The empty-schema preflight meant no existing
curated rows could be deleted. This verified one small execution only, not alias
rekeying, tombstones, the current view, or historical completeness.

## Phase 2 same-attempt idempotency rerun

On 2026-09-30 the guarded rerun called `QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT`
again for the same attempt `20260929T075452Z-26375840ea`. It returned
`status=complete`, `loaded_rows=15`, `processed_rows=15`, `rejected_rows=0`, and
`revision_rows_merged=0` (process attempt `27b80b92c21a47c7b27ecaaf676c0ede`).
Counts stayed at 15 staged rows, 15 revision facts, 45 bridges, three sites, and
one batch fact, while the append-only audit grew from one row to two. The run
also checked unique revision and bridge keys and that the batch fact points to
the new process attempt. This shows idempotency for an unchanged, same-attempt
input only.

## Phase 2 isolated current-view fixture

**View logic on a temporary table (2026-09-30).** The checked-in
`EVENT_CURRENT` SELECT ran against a session-only table shaped like
`FACT_EVENT_REVISION`. Two versions of `uw714110682` returned the later active
revision at magnitude `1.28`; adding a synthetic latest `deleted` revision
returned zero current rows; replaying the old active row still returned zero.
The table ended with four rows (original, update, tombstone, stale replay), and
nothing was written to permanent RAW or curated tables. This verified the view
SQL, not the deployed view or the procedure.

**Fixture database setup (2026-09-30).** A read-only admin
`SHOW DATABASES LIKE` check found the name `QUAKEWATCH_PHASE2_FIXTURE`
available. The guarded setup then created it with `RAW` and `CURATED` schemas
and narrow creation grants for `QUAKEWATCH_ROLE` (`statements_executed: 12`).
Deployment under the project key-pair role passed its empty-schema guard, found
Python 3.12 with pinned `snowflake-snowpark-python` 1.55.0, and reported
`stage_upload: UPLOADED` and `ddl_statements_executed: 16`, creating the
fixture RAW and curated objects and the copied procedure. The synthetic RAW
load then reported one loaded row for each of `fixture-original-v1`,
`fixture-update-v1`, `fixture-deletion-v1`, and `fixture-stale-replay-v1`,
checking each COPY result against attempt-filtered RAW before a complete
synthetic receipt. These are local test fixtures, not USGS data.

**Procedure calls.** Each returned `loaded_rows=1`, `processed_rows=1`,
`rejected_rows=0`, and `revision_rows_merged=1`, with `status=complete` recorded
for the 2026-10-01 calls.

| Attempt | Date | Process attempt ID | Post-call model | `EVENT_CURRENT` |
|---|---|---|---|---|
| `fixture-original-v1` | 2026-09-30 | `542ce981de9d45689e822581a89ee0f7` | 1 staging row, 1 revision fact, 3 bridges, 3 sites, 1 date, 1 magnitude type, 1 status, 1 batch fact, 1 audit | Original active event, magnitude 1.08, expected payload hash |
| `fixture-update-v1` | 2026-10-01 | `36ea2d1efb2144b1a4aad3e107f30842` | 2 staging rows, 2 facts, 6 bridges, 2 batch facts, 2 audits | Later revision, magnitude 1.28, expected payload hash |
| `fixture-deletion-v1` | 2026-10-01 | `5ad657ffe63449d3a3c2b1d37b32ad85` | 3 facts, 9 bridges, 3 batch facts, 3 audits | Zero rows: the latest revision is `deleted`, history kept |
| `fixture-stale-replay-v1` | 2026-10-01 | `516de8b981d7486d85b27ccf1d974fb0` | 4 staging rows, 3 facts, 9 bridges, 4 batch facts, 4 audits | Zero rows: the merge updated the known old revision, and the tombstone still wins |

The curated schema was empty before the first call, so no existing row needed
deletion. The original and stale-replay attempts also form an overlapping-batch
fixture: both request 2026-09-28 UTC with the same event ID, source update time,
and payload hash under different attempt IDs, and the second added no duplicate
revision or bridge key. This is procedure-level evidence for one synthetic
event; it does not prove the catalog-wide sweep captures changes outside a
recent origin-time window, or cover every overlap or mutation.

**Old-origin update (2026-10-01).** The isolated RAW loader staged and copied
`fixture-old-origin-original-v1` and `fixture-old-origin-update-v1`, synthetic
records with a 2020-01-15 origin, returning `loaded_rows=1` each; its post-check
required exactly six one-row RAW attempts and receipts, both new ones complete
and marked synthetic. The guarded original call then raised
`old-origin original model counts differ` after the procedure returned, because
the guard expected two `DIM_DATE` rows and found three: the existing 2026-09-28
plus the event's 2020-01-15 origin and 2020-01-16 source-update dates, which are
correct. The terminal snapshot (five staging rows, four revision facts, 12
bridges, five batch facts, five audits) matched a committed first call. The
combined-pair run then stopped at preflight because the model had already
advanced, so no second call ran. The guard now expects three dates after the
first call and four after the 2026-09-29 update, and the update-only recovery
verifies the exact first-call state before processing.

A read-only diagnostic later showed both attempts with complete audits and the
model at six staging rows, five revision facts, 15 bridges, six batch facts, six
audits, and four dates, with the old-origin event current at magnitude 1.3. The
final read-only guard returned `status=verified`, `old_origin_revisions=2`, and
`current_magnitude=1.3`, checking both payload hashes, retained 2020-origin
history, audits, model counts, the current-view winner, and unique keys. Process
attempts: original `f6ca486374984429974cc8f1e1b5ca15`, update
`78fdae3b5beb47cb8d791a85d8a1eac2`. This shows the model handles an old-origin
update; it does not show the live sweep captured one.

## Phase 2 exit review (2026-10-01)

| Design exit evidence | Current evidence | Status |
|---|---|---|
| Revision selects the later version | Synthetic copied-procedure update retained both facts and selected magnitude 1.28 | Met for the fixture |
| Old-event update outside the initial recent origin-time window | Two synthetic 2020-origin revisions were processed; final read-only guard verified both facts and current magnitude 1.3 | Met for the fixture |
| Tombstone remains in history and hides current event | Synthetic copied-procedure deletion retained three facts and returned zero current rows | Met for the fixture |
| Rerun does not create duplicate logical revisions | Main 15-row same-attempt rerun merged zero revisions; synthetic cross-attempt overlap retained three facts and unique bridge keys | Met for these fixtures |

I confirmed the phase-end checklist on 2026-10-01, opening Phase 3. The broader
Snowflake failure and retry integration check and live nonzero reject evidence
were still open at that point and are not inferred from these calls; the
catalog-wide sweep and source gaps remain separate coverage work.

## Not measured yet

Recorded before Phase 3. Later entries above measured latency, rejects,
pending batches, and some warehouse credits; update-sweep coverage and user
usefulness remain unmeasured.

- Snowflake fetch-to-curated latency, nonzero rejects, and pending batches
- Complete FDSN update-sweep coverage
- Warehouse credit usage
- User task completion time or usefulness

## First history-window attempt

The history plan began as one-year windows. On 2026-09-29 the Seattle window
2021-09-29 through 2022-09-29 failed at the USGS count request with a read
timeout (attempt `20260929T160547Z-b60d35bf44`: `failed`, one unresolved gap for
the full window, no `events.jsonl`). A one-month request, 2021-09-29 through
2021-10-29, then succeeded, and the planner switched to 60 month-sized windows
per site (180 in total) with the same five-year cutoff; its first Seattle window
matches that capture.

### Source captures, first pass (2026-09-29 to 2026-09-30)

Rows are reconciled counts. "Not requested" windows were left for the next run.

| Windows | Attempt IDs | Rows | Outcome |
|---|---|---|---|
| 1 (2021-09-29 to 2021-10-29) | `20260929T161003Z-5d0e466a47` | 167 | Complete; loader later reported `Loaded and reconciled RAW rows: 167` |
| 2 (2021-10-29 to 2021-11-29) | `20260929T162551Z-742a6474a5` | 185 | Complete; loader reported `Loaded and reconciled RAW rows: 185`. A duplicate capture `20260929T162532Z-5cac86e7be` (same logical batch, 185 rows) was not loaded, and a second load of `742a6474a5` stopped at the immutable-receipt guard before PUT or COPY |
| 3 (2021-11-29 to 2021-12-29) | `20260929T163325Z-673ecac05f` | 155 | Complete |
| 4 (2021-12-29 to 2022-01-29) | `20260929T175827Z-70cdef1dcf` failed (sandbox could not resolve the USGS hostname; one gap, zero rows), then `20260929T175854Z-cb9927c2b1` | 193 | Complete on retry |
| 5–7 | `20260929T180021Z-3d2b3c35a7`, `20260929T180023Z-c0b0727a50`, `20260929T180024Z-566cd3c453` | 267, 203, 248 | Complete; seven of 180 captured |
| 8–11 | One 50-window run | 263, 224, 234, 360 | Complete |
| 12 (2022-08-29 to 2022-09-29) | `20260929T181215Z-6db1c7476f`, retry `20260929T181444Z-57b624f069` | 0 | Both timed out after bounded HTTP retries; one gap each. Windows 13–57 not requested; eleven of 180 captured |
| 12 | `20260929T182006Z-2b8d22d8e1` (timeout splitting) | 0 | Failed: splits at `w0001`, `w0001.a`, and `w0001.a.b`; `w0001.a.a` reconciled, `w0001.a.b.a` timed out at the depth limit; one leaf gap |
| 13–15 | `20260930T024713Z-a839f4d513`, `20260930T024715Z-49975e5095`, `20260930T024716Z-5d777c6173` | 259, 244, 204 | Complete, via the explicit start-window option; fourteen of 180 captured |
| 16–24 | One run | 162, 232, 213, 216, 240, 212, 284, 367, 436 (2,362) | Complete |
| 25 (2023-09-29 to 2023-10-29) | `20260930T025128Z-390c1c6b51` | 0 | Interrupted after prolonged read-timeout retries; failed, full-window gap. Windows 26–65 not requested; twenty-three of 180 captured |
| 26–40 | One run | 262, 202, 184, 210, 258, 299, 315, 384, 327, 335, 502, 368, 217, 233, 232 (4,328) | Complete |
| 41 (2025-01-29 to 2025-02-28) | `20260930T032225Z-a2077ba962` | 0 | Interrupted after the signal-based deadline failed to stop retries; failed, one gap. Windows 42–75 not requested; thirty-eight of 180 captured |
| 42 (2025-02-28 to 2025-03-29) | `20260930T041759Z-3de2a8aeda` | 0 | Failed with `SourceDeadlineExceeded`, one gap, confirming the revised deadline. Windows 43–91 not requested |
| 43–71 | One run | 22,467 in 29 manifests | Complete; 43–60 finish Seattle, 61–71 begin San Francisco |
| 72 (2022-08-29 to 2022-09-29) | `20260930T043552Z-b9a86fa447` | 0 | Reached the source deadline; one gap. Windows 73–92 not requested; sixty-seven of 180 captured |
| 73 (2022-09-29 to 2022-10-29) | `20260930T044001Z-39526ae409` | 0 | Reached the three-minute deadline; full-window gap. Windows 74–122 not requested; still 67 of 180 captured |
| 74–123 | One run | 83,844 in 50 manifests | Complete: San Francisco 74–120, Anchorage 121–123; 117 of 180 captured |
| 124–173 | One run | 89,565 in 50 manifests | Complete (Anchorage); 167 of 180 captured |
| 174–180 | One run | 8,574 in seven manifests | Complete; all 180 attempted, 174 captured, gaps at 12, 25, 41, 42, 72, and 73 |

After window 41, the deadline was changed to check the remaining time before
every HTTP request and retry wait; it passed offline tests and was first seen
working live on window 42. A read-only receipt check on 2026-09-29 (no PUT or
COPY) compared the first seven candidates with `BATCH_ATTEMPT` receipts and
attempt-filtered `RAW_EVENT_RECORDS` counts. It found windows 1 and 2 `loaded` with matching local, receipt, and RAW
counts and windows 3–7 `ready` (loaded 2, ready 5, investigate 0).

### Source diagnostics for window 73

All probes used the public San Francisco center and 250 km radius with a
20-second client limit, and returned counts only, not reconciled captures.

| Request | Result |
|---|---|
| One day, 2022-09-29 to 2022-09-30 | `51` |
| Seven days, 2022-09-29 to 2022-10-06, with `includedeleted=true` and `orderby=time-asc` | Timed out (`curl` exit 28) |
| One day with those options | HTTP 400: the manual `curl` omitted `format=geojson`, which `includedeleted` requires (GeoJSON or CSV). The extractor already sends it, so this was a diagnostic-command error; the seven-day timeout also lacked it and says nothing about range size |
| One day, full extractor parameters | `{"count":51,"maxAllowed":20000}` |
| Seven days, full extractor parameters | `{"count":341,"maxAllowed":20000}` |
| One day, 2022-10-20 to 2022-10-21 | `{"count":170,"maxAllowed":20000}` |

### Retries of the gap windows

| Window | Attempt | Result |
|---|---|---|
| 73 | `20260930T045509Z-dced076363` (`--source-days 7`) | Deadline while requesting counts; the manifest could not show which week was active, so incremental child audit was added |
| 73 | `20260930T050144Z-90ed53db7b` (week children) | Children 1–3 reconciled 341, 369, and 354; child `w0001.4` (2022-10-20 to 2022-10-27) hit the deadline; child 5 not requested |
| 73 | `20260930T051517Z-1ee16d7035` (day children) | 26 daily children reconciled 1,451 features; `w0001.27` (2022-10-25 to 2022-10-26) hit the deadline after repeated read-timeout retries used the budget; children 28–30 not requested |
| 12 | `20260930T055443Z-18c52e19c2` (day children) | First ten days reconciled; the eleventh, 2022-09-08 to 2022-09-09 UTC, hit the deadline |
| 25 | `20260930T060246Z-ad1808472c` | All 30 days reconciled, 412 features. **Resolved**; 175 of 180 captured |
| 41 | `20260930T060733Z-f9cbc9f155` | All 30 days reconciled, 255 features. **Resolved**; 176 of 180 captured |
| 42 | `20260930T061111Z-9eb668e522` | First three days reconciled; the fourth, 2025-03-03 to 2025-03-04 UTC, hit the deadline |
| 72 | `20260930T061930Z-748d5f064f` | All 31 days reconciled, 1,348 features. **Resolved**; 177 of 180 captured, leaving 12, 42, and 73 |
| 73 | `20260930T062315Z-1de850b3d1` | Again 26 days reconciled (1,451 features); child 27 hit the deadline |
| 73 | `20260930T073732Z-e3bdce362e` (first with checkpoints) | Child 27 hit the deadline; the first 26 days were saved as 26 checkpoints, each validated for query parameters, content hash, and reconciled counts |
| 73 | `20260930T074227Z-53dd607fef` | Reused all 26 checkpoints (1,451 rows) without refetching; child 27 timed out; zero fresh rows. Confirms checkpoint reuse |
| 12 | `20261001T134425Z-95ee5e220f` | Ten days reconciled again (102 features) and saved as checkpoints for a later `--source-days 1 --resume-children` retry; the eleventh day hit the deadline |
| 12 | `20261001T135022Z-5246138216` (`--resume-children`) | Reused the ten checkpoints, fetched nothing new; the eleventh day exhausted the deadline while fetching counts |
| 12 | `20261001T141455Z-2657c07e44` (`--source-hours 3 --hourly-child 11`) | Reused the ten days; the first two three-hour children of 2022-09-08 reconciled (counts 1 and 0) and were saved as hashed checkpoints; the third, 06:00–09:00 UTC, hit the deadline |
| 73 | `20261001T142252Z-9e2a269c9a` (three-hour children) | Reused the 26 days; reconciled six three-hour children of child 27 (26 new features, six checkpoints); stopped by `KeyboardInterrupt` during `w0001.27.7` (2022-10-25 18:00–21:00 UTC). I then requested no further source retries |

Every failed attempt above is recorded as `failed` with zero monthly JSONL rows,
because a month counts only when every child reconciles; partial progress is
kept as checkpoints, not as coverage. For window 12, an exact-parameter count
for the whole day 2022-09-08 also timed out at 20 seconds, so the blocker is the
USGS count response, not checkpoint reuse or loading. Six-hour count probes
returned `count=1` for `2022-09-08T00:00:00Z` to 06:00, a timeout for 06:00–12:00, `count=1` for
12:00–18:00, and `count=3` for 18:00 to midnight, narrowing the slow slice to
06:00–12:00 UTC. The targeted-hour options were covered offline (reusing an
earlier daily checkpoint, reusing hourly checkpoints after a failure, and
keeping later days on daily requests) before the live attempts above.

### RAW loads

The loader compared each COPY result and attempt-filtered RAW count with the
local manifest before appending a complete receipt. Counts below exclude the
separate 15-row one-day sample and are loader-reported; the verification after
the table confirms them independently.

| Run | Windows loaded | Rows in run | Cumulative windows and rows |
|---|---|---|---|
| Early runs (2026-09-29) | 1 and 2 | 167 and 185 | 2 windows |
| 1 (2026-09-30, 38 candidates inspected) | 36 windows: 3–11, 13–24, 26–40 | 9,544 | 38 windows, 9,896 rows; 0 ready remaining at that point |
| 2 (2026-09-30, 177 candidates validated) | 25, 41, 43–72, 74–91 | 53,931 | 88 windows, 63,827 rows; 89 ready remaining |
| 3 | 92–141 | 88,774 | 138 windows, 152,601 rows; 39 ready remaining |
| 4 | 142–180 (`Loaded 39 windows; 0 ready windows remain.`) | 63,760 | **177 windows, 216,361 rows** |

**Independent verification.** A fresh offline inventory validated all 177
complete local candidates and their 216,361 JSONL rows against their
manifests, with planned windows 12, 42, and 73 missing. A read-only Snowflake
check under the project connection then compared every candidate with its
complete receipt and attempt-filtered RAW count and reported
`loaded=177, ready=0, investigate=0` (no PUT or COPY). Together these confirm
matching load counts for every captured history window.

This completed loading the captured history, not Phase 1: windows 12, 42, and
73 remain gaps, and the catalog-wide update sweep is outstanding.

## First update-sweep bootstrap preparation

**Bootstrap watermark (2026-09-30).** The earliest successful capture was the
one-day sample at `2026-09-29T07:54:52.786Z`; the earliest complete planned
history capture was later, at `2026-09-29T16:10:03.761Z`. No committed update
watermark existed. The proposed bootstrap is the earlier timestamp with an
86,400-second overlap, giving `updatedafter=2026-09-28T07:54:52.786Z`. This is
a starting point, not evidence of a completed sweep.

**Catalog lower bound.** The illustrative 1900 lower bound is not an
earliest-catalog guarantee; USGS documents historical US records from 1568
(https://earthquake.usgs.gov/data/catalog/catalogs/ushis/). Two free probes
with a `0001-01-01T00:00:00Z` bound and the fixed origin cutoff
`2026-09-29T00:00:00Z` (an earliest-event query limited to one feature, then a
count with the proposed `updatedafter`) each timed out after 25 seconds,
settling nothing. Bounded probes for `1568-01-01` through `1569-01-01` and
`0001-01-01` through `0002-01-01`, with the same `updatedafter`, GeoJSON,
deletion, and ordering parameters, each returned HTTP 200 with
`{"count":0,"maxAllowed":20000}`. That confirms year 0001 is accepted for a
bounded count, but not full-range performance or the absence of older events
without the update filter. `0001-01-01T00:00:00Z` is therefore the explicit
operational lower bound for the first sweep, with earlier dates outside
coverage; it is not asserted to be the earliest ComCat event. A real sweep
freezes its start time and origin cutoff at launch.

**Live sweep attempts (2026-09-30).** Each used lower bound
`0001-01-01T00:00:00Z`, prior bootstrap watermark `2026-09-29T07:54:52.786Z`,
and a 24-hour overlap. Each ended `failed` with zero written rows, no
`events.jsonl`, `watermark_advanced: false`, and no Snowflake call.

| Attempt | Cutoff (`sweep_started_at`) | Slicing | Result |
|---|---|---|---|
| `20260930T083733Z-39c5aab2e8` | `2026-09-30T08:37:33.423Z` | Whole catalog in one request | The count/fetch recursion exceeded the three-minute deadline; conservative gap over the full range |
| `20260930T084645Z-78885cdc4c` | `2026-09-30T08:46:45.273Z` | 50-year slices | First 40 children (0001-01-01 to 2001-01-01) reconciled with three features; `w0001.41` (2001-01-01 to the cutoff) hit the deadline |
| `20260930T085553Z-b0fc15d463` | Not recorded | 50-year slices before 2001, five-year after | 44 children reconciled and one split parent; `w0001.45` (2021-01-01 to 2026-01-01) hit the deadline |
| `20260930T090821Z-62080fb212` | Not recorded | One-year recent slices | Failed before reaching USGS: the sandbox could not resolve the hostname. Not coverage evidence |
| `20260930T090855Z-67fd18f18e` | Not recorded | One-year recent slices | 62 children reconciled, one split parent; gap for 2023-01-01 to 2024-01-01 after the deadline |
| `20260930T091846Z-31d7a86ca6` | Not recorded | Monthly recent slices | 71 children reconciled (574 audited features, not a completed capture); the October 2023 child, `2023-10-01` to `2023-11-01`, hit the deadline |
| `20260930T095900Z-2fb588dc8d` (first with checkpoints) | `2026-09-30T09:59:00.481Z` | Monthly recent slices | Saved 71 reconciled child checkpoints (574 audited features) with payloads, audit counts, fetch times, and checksums; the October 2023 child `w0001.72` hit the deadline |
| `20260930T100803Z-cf8e520655` (same frozen sweep) | `2026-09-30T09:59:00.481Z` | Daily slices for October 2023 | Validated and reused all 71 checkpoints and saved eight new daily ones for October 1–8, giving 79 reconciled child audits; the October 9–10 UTC child `w0001.80` hit the deadline. Live evidence that sweep checkpoint reuse works |

**Diagnostics for October 2023.** All requests used the sweep's update
filter, GeoJSON format, deletion flag, and ordering, and returned counts only.
No features were captured, nothing was loaded, and no watermark advanced.

| Request (2023 UTC) | Result |
|---|---|
| October 1–8, one request | Timed out at the 20-second client limit; no data |
| October 1 (2023-10-01 to `2023-10-02`), then October 2–7, one day each | HTTP 200 with `{"count":0,"maxAllowed":20000}` for each, so all seven days returned zero while the combined week timed out, pointing to range-sensitive source response time |
| The other 24 October days, one day each | Zero for 23 days; October 9–10 timed out at 20 seconds, so its count is unknown. That makes 30 daily zero counts in all, none a substitute for a reconciled capture |
| October 9–10, repeated | Timed out again |
| October 9, half days | 00:00–12:00 timed out; 12:00 to October 10 00:00 returned zero |
| October 9, 00:00–06:00 and 06:00–12:00 | First timed out; second returned zero |
| October 9, one-hour probes from 00:00 to 06:00 | Zero for 00:00–01:00, 01:00–02:00, and 03:00–06:00; 02:00–03:00 timed out |
| October 9, 02:00–02:30 and 02:30–03:00 | First timed out; second returned zero |
| October 9, five-minute probes from 02:00 to 02:30 (12-second limit) | Zero for five of six; 02:20–02:25 timed out |
| October 9, one-minute probes from 02:20 to 02:25 | Zero for 02:20–02:21 and 02:22–02:25; 02:21–02:22 timed out |
| October 9, 02:21–02:22, GeoJSON event query instead of count | Timed out after 20 seconds |

Both the count and event-query endpoints failed to answer for the minute
October 9 02:21–02:22 UTC, so this is recorded as a source-response gap rather
than a count-endpoint problem alone. Manual subdivision then stopped. These are
diagnostic results, not reconciled gap boundaries in a sweep manifest, and no
zero count or completeness is claimed for the unanswered intervals.
