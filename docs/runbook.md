# Runbook

## Local setup

1. Install Python 3.12 and `uv`.
2. From the repository root, run `uv sync --locked --no-editable`.
3. Run a small, explicit time range before requesting a multi-year history.

The non-editable install is used because the editable-package path was not loading correctly in this local environment. After changing package code, run `uv sync --locked --no-editable --reinstall-package quakewatch` to rebuild the installed wheel; a plain `uv sync` can report everything checked while leaving an older wheel installed.

Phase 1 also locks the Snowflake Python Connector for the planned batch loader. Installing it locally does not connect to Snowflake or start warehouse compute. The loader will read the existing project key-pair profile outside Git and ask for the encrypted key passphrase locally; do not put that passphrase in a command, config file, or chat.

## Fetch a bounded batch

```sh
uv run quakewatch-extract \
  --site seattle \
  --start 2026-09-28T00:00:00Z \
  --end 2026-09-29T00:00:00Z
```

Supported public demo sites are `seattle`, `san-francisco`, and `anchorage`. Times without an explicit zone are interpreted as UTC. Output goes to `data/raw/<attempt-id>/` unless `--output` is provided. Keep private coordinates and credentials out of the repository.

Before the five-year initial history, preview its fixed origin-time requests with `PYTHONPATH=src .venv/bin/python -m quakewatch.history_plan --cutoff 2026-09-29T00:00:00Z`. It prints 60 contiguous month-sized windows for each public site (180 total) without contacting USGS or Snowflake. The earlier year-sized Seattle count request timed out, while its first month reconciled, so the initial request size was reduced. The extractor still checks each request's USGS count and splits a window when needed. The previously loaded one-day Seattle sample overlaps the final history window; later revision processing must deduplicate source observations across attempts.

Use `PYTHONPATH=src .venv/bin/python -m quakewatch.history_plan --cutoff 2026-09-29T00:00:00Z --resume-preview` to see the first month without a complete local manifest and event file. This is a local capture inventory only; it does not query Snowflake or prove a capture was loaded. Failed manifests remain visible in their attempt folders and are not counted as complete.

Preview a bounded extraction run with `PYTHONPATH=src .venv/bin/python -m quakewatch.history_plan --cutoff 2026-09-29T00:00:00Z --resume --max-windows 50`. Add `--execute` only when ready to contact USGS. The limit must be 1–50 windows per invocation. The command stops at the first failed manifest and reports its path; rerun after inspecting the coverage gap. It does not upload to Snowflake or check which captures were loaded there.

When a month remains unresolved after bounded retries, use an explicit `--start-window 13` with `--resume` to continue from a later month. The skipped window stays uncaptured and visible in `--resume-preview`; the resulting history must be reported as incomplete until that gap is reconciled. This option does not mark skipped windows complete or change existing manifests.

Inventory and validate the local files eligible for a RAW load with `PYTHONPATH=src .venv/bin/python -m quakewatch.history_load_plan --cutoff 2026-09-29T00:00:00Z`. It prints one selected attempt and expected row count per captured history window. Every line is a **candidate**, not proof of an outstanding load: this command makes no Snowflake connection, so previously loaded attempts may appear. Check Snowflake receipts before any future bulk load.

After explicit approval for any possible warehouse cost, add `--check-snowflake` to that command. It prompts locally for the project key passphrase, reads `BATCH_ATTEMPT` and attempt-filtered RAW counts, and labels candidates `loaded`, `ready`, or `investigate`. `loaded` requires one complete receipt and matching receipt/RAW/local row counts; `ready` requires no receipt and no RAW rows. Any failed or duplicate receipt, or count mismatch, is `investigate` and must not be bulk loaded. The check performs SELECT only, with no PUT or COPY.

Preview the bounded RAW loader with `PYTHONPATH=src .venv/bin/python -m quakewatch.history_raw_load --cutoff 2026-09-29T00:00:00Z --max-windows 50`. This only validates local candidates. After explicit cost approval, add `--execute`; it connects once, checks all candidate receipts and RAW counts, and loads at most 50 `ready` attempts in window order. It rechecks each selected attempt immediately before PUT/COPY and stops on any `investigate` state or load error. The limit must be 1–50; rerunning skips attempts with matching complete receipts. This command does not extract new USGS windows.

Add `--window 1` to preview only the first Seattle month, 2021-09-29 through 2021-10-29. Add `--execute` with an explicit window number to fetch just that one range into an attempt-specific `data/raw/` directory; it does not load Snowflake. Inspect its manifest and counts before choosing another window. The command refuses `--execute` without `--window` so the full history cannot start accidentally. The first month is already captured as attempt `20260929T161003Z-5d0e466a47`; do not re-fetch it just to advance the plan.

The extractor targets fewer than 10,000 features per leaf request, giving headroom below the USGS 20,000-result service limit. At a count of 10,000 or more it splits the time window before fetching features; the source may still change between count and fetch, so before/after count reconciliation remains required.

If the source count or feature request repeatedly times out, the extractor now splits that time window into smaller audited requests, up to three timeout split levels. It still compares before/fetched/after counts on each leaf. If a leaf continues timing out, the attempt fails with an unresolved coverage gap; partial sibling rows are not written as a complete capture. This responds to the two saved window-12 timeout attempts without erasing them.

For a known slow month, add `--source-days 7` to an explicit `history_plan --window N --execute` (or a bounded `--resume --max-windows N --execute`) command. The logical monthly batch stays the same, while the extractor begins with contiguous, overlapping-at-boundary source calls of at most seven days. The manifest records the planned parent split and every child count/fetch result. Every child must reconcile before the monthly attempt is complete; a failed child leaves the month unresolved and writes no partial file. This option is based on the exact-parameter seven-day San Francisco count that returned 341 on 2026-09-30; its live feature capture has not yet been verified.

For repeated daily retries, add `--source-days 1 --resume-children` to an explicit history window. Each successfully reconciled child is saved atomically under its attempt's ignored `data/raw/<attempt-id>/children/` folder. A later attempt reuses only a checkpoint with the same logical batch, slice size, query parameters, intact content hash, and reconciled child counts. The new manifest labels reused children with their original attempt ID, and records fresh and reused row totals separately; each output row keeps its original child fetch time. A failed monthly attempt still writes no `events.jsonl` and remains an explicit coverage gap. A successful month can combine prior reconciled children with newly fetched children; this is best-effort source reconciliation across times, not a transactionally consistent USGS snapshot. The update sweep must still detect later source changes. Earlier attempts made without `--resume-children` have no feature checkpoints and must be fetched again once before later reuse is possible.

During a week-sliced capture, `manifest.json` now records `active_window` and saves each completed child audit before beginning the next. If the deadline or an interruption occurs, the failed manifest retains the reconciled child audits and marks the active child as unresolved. The attempt still writes no partial `events.jsonl`; rerun it as a new attempt after investigating the gap.

After the one-day-sliced window-73 attempt spent its remaining deadline on repeated reads of October 25–26, consecutive HTTP read timeouts were capped at two attempts. This gives recursive time splitting a chance before the monthly budget expires. Other temporary transport errors and retryable HTTP statuses retain the four-attempt cap. A completed month still requires before/fetch/after reconciliation for every leaf.

Each source window has a 180-second wall-clock budget shared by its HTTP retries and splits. Before each request and retry wait, the extractor checks the remaining time and caps the request timeout to it. If the budget expires, the attempt is marked failed with zero written rows and an explicit full-window unresolved gap. An interrupted command is audited the same way. A 50-window run still stops at that failed month; use an explicit later `--start-window` to continue while keeping the gap visible.

## Inspect a run

Read `manifest.json` first. A successful manifest has status `complete`; each leaf query window should show matching `count_before`, `returned_rows`, and `count_after`. A failed source window appears in `coverage_gaps` with its ID, bounds, and reason; `window_audit` also retains parent split and earlier sibling results. A failed run writes no event file and needs investigation and retry. The source is not a durable event log, and a successful response does not prove gap-free catalog coverage.

## Snowflake access

The local Snowflake CLI admin connection works. The [Phase 0 bootstrap SQL](../sql/phase0_bootstrap.sql) created the dedicated role, empty database/schemas/internal stage, and XS warehouse on 2026-09-29. Metadata checks confirmed the warehouse is suspended and the role has the intended grants. The named public key `QUAKEWATCH_KEY` is registered and restricted to `QUAKEWATCH_ROLE`; `snow connection test -c quakewatch_project` succeeded with the encrypted local private key. See the [Phase 0 environment check](environment.md) for evidence and remaining Phase 1/2 checks. Store authentication material outside Git. Do not paste private keys or passwords into chat or commit them.

## Phase 1 raw tables

The [raw-table SQL](../sql/phase1_raw_tables.sql) created `QUAKEWATCH.RAW.BATCH_ATTEMPT` and `QUAKEWATCH.RAW.RAW_EVENT_RECORDS` under `QUAKEWATCH_ROLE` on 2026-09-29. `DESCRIBE TABLE` confirmed 21 and 10 columns respectively, including the full-source `PAYLOAD VARIANT`. Seattle attempts with 15, 167, and 185 rows were loaded on 2026-09-29; see [results](results.md). Repeat-run and wider history evidence remain pending.

The [RAW COPY mapping](../sql/phase1_copy_raw.sql) selects each JSONL record's capture metadata and full `source_feature`, plus Snowflake's staged filename and file row number. It ran for the first Seattle attempt. Its `attempt_id` template value names the unique stage directory containing that attempt's `events.jsonl`. Reconcile the COPY result and RAW row count against the completed manifest before recording a successful load.

Before staging, `validate_local_batch` checks that the manifest is complete, has no coverage gaps, and matches every local JSONL row and its count. After COPY, `reconcile_loaded_rows` requires both the COPY loaded-row count and the attempt-filtered RAW row count to equal that local count. The loader invokes both checks and appends a batch receipt after reconciliation.

To inspect the first upload plan without connecting to Snowflake, run `PYTHONPATH=src .venv/bin/python -m quakewatch.raw_load data/raw/20260929T075452Z-26375840ea/manifest.json`. It checks the local envelope and prints the attempt-specific stage path and expected row count. The generated PUT/COPY statements are prepared for the later loader; this command does not execute them.

The Python Connector boundary reads only `quakewatch_project` from the local Snowflake CLI config, verifies its key-pair authenticator and `QUAKEWATCH_ROLE`, and prompts for the encrypted key passphrase in the terminal when a live run is explicitly started. It never reads the admin profile or takes the passphrase from a command-line argument.

For read-only row checks, use this Python Connector boundary too. The installed Snowflake CLI `snow sql -c quakewatch_project` does not prompt for the encrypted key passphrase and fails unless that passphrase is supplied through CLI configuration or environment; do not place it in chat or shell history. The connector prompts privately in the terminal. The first independent check found one complete receipt and 15 RAW rows for the Seattle attempt.

The loader has an explicit `--execute` path. It checks for an existing attempt receipt or RAW rows, uploads one new file, runs the COPY mapping, compares COPY and attempt-filtered RAW counts with the local manifest, then appends a `BATCH_ATTEMPT` receipt. A COPY or count failure appends a failed receipt if the connection still permits it; a retry needs a new extraction attempt ID. The command without `--execute` remains read-only. Ask for warehouse-cost approval before each live run.

## Phase 2 procedure bundle

The Phase 2 procedure can be bundled offline with `PYTHONPATH=src .venv/bin/python scripts/build_procedure_bundle.py`. It writes `data/procedure/quakewatch_procedure.zip`, an ignored local artifact, and prints its SHA-256. The [procedure definition](../sql/phase2_create_procedure.sql) expects that ZIP at `@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure/quakewatch_procedure.zip`. Uploading it, creating the procedure, and calling it are separate live steps requiring explicit approval for possible warehouse cost and for the collision handler's curated-row deletions. Do not run the SQL before the stage import exists.

The [first pilot plan](phase2-pilot-plan.md) narrows deployment to the already loaded 15-row Seattle attempt. `PYTHONPATH=src .venv/bin/python scripts/phase2_pilot.py` prints its checks and DDL order without connecting. Its `--execute` mode requires explicit cost approval; it stops unless the curated schema is empty and the RAW receipt/count reconcile, then performs one procedure call and count check.

The first pilot completed on 2026-09-30: 15 staged rows, 15 revision rows, 45 bridge rows, one batch fact, one process attempt, and three public sites. See [measured results](results.md). The pilot command is intentionally first-run only; its empty-schema guard now stops a second execution. Do not rerun it to process more attempts. A separate, guarded processing command and acceptance checks are needed before wider history processing.

The [one-attempt rerun plan](phase2-rerun-plan.md) uses `PYTHONPATH=src:. .venv/bin/python scripts/phase2_rerun_check.py` for an offline preview. Its approved `--execute` run completed on 2026-09-30: zero revisions merged, model counts unchanged, and a second processing audit appended. See [measured results](results.md). Its first-pilot-state guard now prevents another live execution.

Preview the [isolated current-view fixture check](phase2-current-fixture-plan.md) with `PYTHONPATH=src:. .venv/bin/python scripts/phase2_current_fixture.py`. It does not connect or modify Snowflake. The separately approved `--execute` mode will use a temporary revision table for a synthetic update, tombstone, and stale replay; it does not load fixtures into permanent RAW or curated tables or call the procedure. No live fixture check has run yet.

## Update-sweep preview

`quakewatch.update_plan` prints a local plan only. Supply the catalog origin-time lower bound, a fixed origin-time cutoff, the prior committed update watermark, the sweep start, and a positive overlap in seconds. The resulting `updatedafter` is the prior watermark minus overlap; no spatial or magnitude filters are added. The proposed next watermark is the fixed sweep start. The planner does not persist or advance any watermark and does not count-size, extract, or load windows yet. Execution must verify all bounded source windows and their RAW loads before a later implementation can commit that watermark; failed or incomplete sweeps must retain the previous one.

This offline example uses illustrative inputs, **not an established production watermark or an approved catalog coverage boundary**. The first live sweep still needs an explicit bootstrap watermark and catalog lower-bound decision based on the history capture dates and required source coverage.

```bash
PYTHONPATH=src .venv/bin/python -m quakewatch.update_plan \
  --catalog-start 1900-01-01T00:00:00Z \
  --cutoff 2026-09-30T00:00:00Z \
  --last-watermark 2026-09-29T00:00:00Z \
  --sweep-started-at 2026-09-30T00:00:00Z \
  --overlap-seconds 86400
```

Expect `status: preview`, `updatedafter: 2026-09-28T00:00:00.000Z`, and `watermark_advanced: false`. Dates before the configured catalog lower bound are outside this plan. The source does not provide a transactionally consistent snapshot. See the [USGS parameter contract](https://earthquake.usgs.gov/fdsnws/event/1/) for the distinction between origin time and update time.

## Update-sweep extraction

`PYTHONPATH=src .venv/bin/python -m quakewatch.update_extract` accepts the same five required planning arguments. Without `--execute` it only prints the plan. Adding `--execute` performs a bounded source capture: it uses the shared extractor to split origin-time windows by counts, preserves the same `updatedafter` on every child, includes deletions, and applies no spatial or magnitude filters. Every leaf compares source counts before/after against returned features. One three-minute deadline bounds the entire attempt. Split boundaries overlap deliberately; later revision processing must deduplicate observations.

Each execution writes a unique attempt manifest under ignored `data/raw/`, with `batch_kind: update_sweep`. A successful extraction atomically publishes `events.jsonl` in the existing RAW-loader format. Failure records an explicit coverage gap and cannot be loaded as complete. A deadline failure may conservatively identify the whole requested range when no completed recursive audit is available. `last_committed_watermark` and `watermark_advanced: false` remain unchanged on success and failure: extraction alone does not authorize a watermark commit. The load-and-commit workflow is not implemented yet. History loading commands intentionally exclude catalog-wide sweep attempts.

Offline verification:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_update_extract tests.test_update_plan \
  tests.test_extract_batch tests.test_raw_load -q
```

On 2026-09-30 these 38 tests passed, including mocked over-limit splitting with an old deleted record, source failure/deadline evidence, and local loader compatibility. No live update-sweep extraction or Snowflake sweep load has been demonstrated yet.

## Sweep load and watermark completion

Use `PYTHONPATH=src .venv/bin/python -m quakewatch.update_load <sweep-manifest>` to validate a completed sweep locally. Preview mode does not connect or write state. Execution requires cost approval and `--execute`; the first committed sweep also requires `--initial-watermark` matching its explicitly chosen bootstrap watermark.

The runner validates contiguous audited origin-time coverage, each leaf's before/returned/after counts, and local rows per window. It checks the prior committed watermark before loading. It then loads a ready attempt or recognizes a previously loaded attempt, rereads its complete receipt and RAW total, compares the stored receipt manifest with the local manifest, and checks RAW counts per window. Only after all checks pass does it atomically replace `data/watermarks/update.json`, recording the sweep start as the committed watermark and retaining the prior watermark and source attempt ID. Each attempt's original manifest remains unchanged. A file lock serializes this single-Mac writer; the local state and lock must not be shared across hosts. Back up local state with the ignored raw data. A changed catalog lower bound or backward cutoff requires investigation, not silent reuse.

If loading fails or counts disagree, the prior state remains. If loading succeeds but local state writing fails, rerunning the same attempt can verify its existing receipt and complete the state write without another COPY. A stale sweep whose prior watermark no longer matches is rejected. No automatic watermark is inferred from the history load. This workflow has offline evidence only; no live sweep load or watermark commit has run.

For a catalog sweep with a broad origin-time lower bound, `update_extract` now starts with contiguous origin-time slices of at most 50 years (`--years-per-window 1..100` changes the initial size). Each slice retains the same fixed `updatedafter`, deletion, and ordering parameters. The extractor still recursively splits any over-limit, mismatched, or timed-out slice and reconciles all leaves. It saves completed child audits as it goes. If the three-minute attempt deadline expires, the failed manifest names the active planned slice and retains earlier completed audits; it still writes no partial `events.jsonl`, so the entire sweep remains incomplete and its watermark unchanged. This initial partition is an operational request size, not a change to the catalog lower bound. As of 2026-09-30 it is tested offline; no live partitioned sweep result is claimed.

After the live sweep narrowed the slow request to 2001–2026, initial partitioning was refined: the default remains 50-year slices before `--recent-start-year 2001`, then uses `--recent-years-per-window 5`. For the year-0001 lower bound and a 2026 cutoff this makes 46 contiguous windows, with five-year recent slices and a final partial slice. These are initial source request sizes; source count limits, recursive splitting, the fixed update filter, and full-sweep reconciliation still apply. The values are configurable through `--years-per-window`, `--recent-start-year`, and `--recent-years-per-window`. Live five-year and one-year attempts both left explicit source gaps; see `docs/results.md`.

Live retries narrowed the timeout to origin year 2023. Set `--recent-years-per-window 1 --monthly-start-year 2023 --recent-months-per-window 1` to request one-year slices from 2001 through 2022 and month-sized slices from 2023 onward. The optional monthly mode changes initial request boundaries only; a complete sweep still needs every child reconciled before RAW loading or watermark advancement. Its boundary behavior has offline tests; the first live monthly attempt narrowed the gap to October 2023, as recorded in `docs/results.md`.

For future live update-sweep attempts, add `--resume-children` and keep the same frozen `--cutoff`, `--sweep-started-at`, catalog lower bound, prior watermark, and overlap on retries. Each completed initial child saves its reconciled feature rows, audit, source fetch time, and checksum under the ignored attempt directory. A retry reuses a child only when its window ID and full bounded query parameters match, its saved checksum and row counts validate, and the frozen sweep start matches. A changed or damaged child is fetched again. Reused rows retain their original source fetch time; failed attempts still have no `events.jsonl` and cannot load or advance the watermark. Attempts made before this option existed saved audits but no feature checkpoints, so their nonzero windows cannot be reconstructed from those audits. The reuse path passed offline tests and a live retry reused 71 validated children; see `docs/results.md`.

For the measured October 2023 timeout, add `--daily-month 2023-10` to split that calendar month into one-day initial windows. Earlier initial window IDs and query bounds stay the same, so a retry of the frozen `2026-09-30T09:59:00.481Z` sweep reused its 71 saved children. Any October day that fails still leaves an explicit gap and prevents a completed sweep or watermark commit. The live retry saved October 1–8 and timed out on October 9; see `docs/results.md`.
