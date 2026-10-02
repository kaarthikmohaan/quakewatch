# Results summary

This page summarises what QuakeWatch has measured, with each design target
next to the evidence for it. The dated, step-by-step record, including
Snowflake query IDs, hashes, and every failed attempt, is in the
[results evidence log](evidence/results-log.md).

Live work ran between 29 September and 2 October 2026 on a personal Snowflake
account. Counts are source observations, not unique earthquakes, and are not
official USGS totals.

## Headline numbers

| Measure | Result | Evidence |
|---|---|---|
| History windows loaded and reconciled | **177 of 180** planned windows; windows 12, 42, and 73 timed out even after splitting and are recorded as gaps | [Capture log](evidence/results-log.md#first-history-window-attempt) |
| RAW rows loaded | **216,361** history rows, plus an overlapping 15-row Seattle sample | [RAW loads](evidence/results-log.md#first-history-window-attempt) |
| Batch receipts reconciled | **All 179** receipts (216,391 observations, including two overlapping 15-row Seattle samples): RAW = staged = processed + rejected | [2 October check](evidence/results-log.md#live-end-to-end-seattle-demo-2026-10-02) |
| Rejected rows | **485**, all USGS placeholder ("stub") records, stored as `source_stub_record`; see [reject analysis](#reject-analysis) | [Quality deployment](evidence/results-log.md#first-phase-3-quality-deployment-attempt) |
| Duplicate revision or site-bridge key groups | **0** | [Uniqueness check](evidence/results-log.md#first-phase-3-uniqueness-check) |
| First-backfill fetch-to-curated p95 | **35.9 hours, missing the 24-hour target** set before measuring (178 attempts) | [Measurement plan and result](evidence/results-log.md#phase-3-first-backfill-measurement-plan-set-before-live-query) |
| Failed transform, rollback, and retry from RAW | **Passed**; identical counts before failure, after rollback, and after retry | [Retry drill](evidence/results-log.md#isolated-failed-transform-and-retry-drill) |
| Clone isolation and Time Travel recovery | **Passed** on a five-row fixture table; demo clone dropped | [Recovery drill](evidence/results-log.md#phase-4-clone-isolation-and-time-travel-drill) |
| Cortex briefs passing human fact review | **9 of 9** in the evaluation; **4 other briefs rejected** by fact checks (2 before it, 2 in the [2 October demo](evidence/results-log.md#live-end-to-end-seattle-demo-2026-10-02)), with SQL used instead | [Cortex evaluation](evidence/results-log.md#phase-4-nine-case-cortex-evaluation) |
| Measured Cortex cost | **0.003948756** AI credits for the first 11 completed calls, separate from warehouse compute; the 2 October calls are unmeasured | [Cortex evaluation](evidence/results-log.md#phase-4-nine-case-cortex-evaluation) |
| Warehouse usage snapshot | **0.088875** credits for one fully reported hour (shared warehouse; not a per-demo bill) | [Metering snapshot](evidence/results-log.md#phase-4-warehouse-metering-snapshot) |
| Secret-free tests | **328**, run in GitHub Actions with ruff and mypy on every push (303 at the published Phase 4 run) | [CI workflow](../.github/workflows/ci.yml), [first CI run](evidence/results-log.md#first-github-actions-fixture-run) |

## Design targets and status

These are the success criteria from the [design](design.md#definition-of-success).

| Target | Status | Evidence |
|---|---|---|
| Every batch records its range, parameters, counts, fetch time, outcome, and gaps | **Met** | Manifests and `BATCH_ATTEMPT` receipts for all 178 attempts |
| RAW keeps the full source record and batch metadata | **Met** | Full GeoJSON payload stored as VARIANT with attempt and file metadata |
| Re-running a batch adds no duplicate logical revisions | **Met** for tested cases | Same-attempt rerun merged zero revisions; cross-attempt overlap fixture kept unique keys |
| An old-event revision found by the update sweep updates history and the current view | **Partly met** | Proven on synthetic fixtures; the live catalog-wide sweep has not completed |
| A deletion is kept as a tombstone and cannot be resurrected | **Met** for fixtures | Deletion retained three facts and hid the current event; stale replay did not restore it |
| A failed transform retries from RAW without refetching | **Met** | Isolated and first-ever-failure drills |
| The update watermark advances only after full reconciliation | **Held** | The sweep is incomplete, so the watermark has correctly not advanced |
| Table grains and keys are documented and checked in SQL | **Met** | [Data dictionary](data-dictionary.md); zero duplicate key groups |
| Loaded, rejected, and pending rows, gaps, and latency are reported separately | **Met** | Health and reconciliation views; latency measured separately |
| Targets are set before measuring, and results are published either way | **Met** | The 24-hour p95 target was set first and the miss is reported |
| One target analyst confirms the comparison task is useful | **Not done** | [Interview guide](target-user-interview.md) prepared; no session held |

## Phase exits

| Phase | Outcome |
|---|---|
| 0. Source and account check | Snowflake role, stage, and Snowpark runtime verified; see [environment check](evidence/phase0-environment-check.md) |
| 1. Batch extract and raw load | 177 of 180 history windows loaded; 3 source gaps; update sweep incomplete |
| 2. Warehouse models | Revision, old-event update, tombstone, and rerun fixtures passed ([exit review](evidence/results-log.md#phase-2-exit-review-2026-10-01)) |
| 3. Quality and evidence | Reconciliation, uniqueness, CI, and sample analysis passed; latency target missed ([exit review](evidence/results-log.md#phase-3-exit-review)) |
| 4. Optional demos | Clone and Time Travel drill passed; Cortex evaluated; usage measured ([exit review](evidence/results-log.md#phase-4-exit-review), [close-out](evidence/phase4-closeout.md)) |

## Reject analysis

All 485 rejected rows were investigated on 2 October 2026 by replaying the
saved local extracts through the staging parser, without connecting to
Snowflake. Every one is a USGS placeholder ("stub") feature:

| Property | Finding |
|---|---|
| Source network | 481 `ak` (Alaska), 4 `av` (Alaska Volcano Observatory) |
| Content | Title `M ?`; no origin time, magnitude, or status; coordinates `[0, 0]` |
| Link to real events | All 485 stub IDs are listed as alias IDs of full records, and all 493 IDs the stubs point to belong to full records |
| Effect of rejecting them | No earthquake is lost; alias resolution already gets the same links from the full records |

Parser version 1 labelled them `invalid_origin_time`, which described the
symptom rather than the cause. [Parser version 2](../src/quakewatch/staging.py)
labels them `source_stub_record` and also rejects an active record whose
coordinates are the `[0, 0]` placeholder, while keeping a deleted record at
that placeholder as a tombstone without coordinates. Replaying all 216,591
local rows through version 2 gives the same 485 rejects, now as
`source_stub_record`, and no other changes. On 2 October 2026 the stored
Snowflake rows were migrated to match: after checks confirming every reject was
a stub payload, one transaction relabelled exactly 485 rows and marked all
staging and fact rows as version 2 ([release record](evidence/results-log.md#parser-version-2-release-2026-10-02)).

## Latency evidence

Fetch-to-curated latency has one measured sample: the 178-attempt first
backfill, where curation was run manually in bulk after loading (p95 35.9
hours). It does not describe steady-state latency. A second sample needs
scheduled runs that process each batch soon after it loads; this is listed
under [still open](#still-open).

## Still open

- **Source gaps:** history windows 12, 42, and 73.
- **Update sweep:** one bounded source request times out, so the catalog-wide
  sweep has not completed and its watermark has not advanced.
- **Latency:** steady-state latency is unmeasured; only the first manual
  backfill was measured.
- **Cost:** warehouse credits were captured as a shared hourly snapshot, not
  per run; storage was not measured.
- **User validation:** no target-analyst session has been held.

## Evidence log contents

The [evidence log](evidence/results-log.md) is ordered newest first. Its
sections are:

- [Parser version 2 release (2026-10-02)](evidence/results-log.md#parser-version-2-release-2026-10-02)
- [Live end-to-end Seattle demo (2026-10-02)](evidence/results-log.md#live-end-to-end-seattle-demo-2026-10-02)
- [Phase 4 ten-case Cortex aggregate snapshot](evidence/results-log.md#phase-4-ten-case-cortex-aggregate-snapshot)
- [Phase 4 nine-case Cortex evaluation](evidence/results-log.md#phase-4-nine-case-cortex-evaluation)
- [Phase 4 Cortex trial attempt](evidence/results-log.md#phase-4-cortex-trial-attempt)
- [Phase 4 exit review](evidence/results-log.md#phase-4-exit-review)
- [Phase 4 sandbox recovery preflight](evidence/results-log.md#phase-4-sandbox-recovery-preflight)
- [Phase 4 clone isolation and Time Travel drill](evidence/results-log.md#phase-4-clone-isolation-and-time-travel-drill)
- [Phase 4 warehouse metering snapshot](evidence/results-log.md#phase-4-warehouse-metering-snapshot)
- [Phase 3 first-backfill measurement plan (set before live query)](evidence/results-log.md#phase-3-first-backfill-measurement-plan-set-before-live-query)
- [First GitHub Actions fixture run](evidence/results-log.md#first-github-actions-fixture-run)
- [Phase 3 exit review](evidence/results-log.md#phase-3-exit-review)
- [Isolated failed-transform and retry drill](evidence/results-log.md#isolated-failed-transform-and-retry-drill)
- [Window 73 checkpoint retry after Phase 3 exit](evidence/results-log.md#window-73-checkpoint-retry-after-phase-3-exit)
- [First Phase 3 quality deployment attempt](evidence/results-log.md#first-phase-3-quality-deployment-attempt)
- [First Phase 3 uniqueness check](evidence/results-log.md#first-phase-3-uniqueness-check)
- [First live source capture](evidence/results-log.md#first-live-source-capture)
- [First RAW load](evidence/results-log.md#first-raw-load)
- [First Phase 2 Snowpark pilot](evidence/results-log.md#first-phase-2-snowpark-pilot)
- [Phase 2 same-attempt idempotency rerun](evidence/results-log.md#phase-2-same-attempt-idempotency-rerun)
- [Phase 2 isolated current-view fixture](evidence/results-log.md#phase-2-isolated-current-view-fixture)
- [Phase 2 exit review (2026-10-01)](evidence/results-log.md#phase-2-exit-review-2026-10-01)
- [Not measured yet](evidence/results-log.md#not-measured-yet)
- [First history-window attempt](evidence/results-log.md#first-history-window-attempt)
- [First update-sweep bootstrap preparation](evidence/results-log.md#first-update-sweep-bootstrap-preparation)
