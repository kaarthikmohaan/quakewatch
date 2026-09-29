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

Add `--window 1` to preview only the first Seattle month, 2021-09-29 through 2021-10-29. Add `--execute` with an explicit window number to fetch just that one range into an attempt-specific `data/raw/` directory; it does not load Snowflake. Inspect its manifest and counts before choosing another window. The command refuses `--execute` without `--window` so the full history cannot start accidentally. The first month is already captured as attempt `20260929T161003Z-5d0e466a47`; do not re-fetch it just to advance the plan.

The extractor targets fewer than 10,000 features per leaf request, giving headroom below the USGS 20,000-result service limit. At a count of 10,000 or more it splits the time window before fetching features; the source may still change between count and fetch, so before/after count reconciliation remains required.

## Inspect a run

Read `manifest.json` first. A successful manifest has status `complete`; each leaf query window should show matching `count_before`, `returned_rows`, and `count_after`. A failed source window appears in `coverage_gaps` with its ID, bounds, and reason; `window_audit` also retains parent split and earlier sibling results. A failed run writes no event file and needs investigation and retry. The source is not a durable event log, and a successful response does not prove gap-free catalog coverage.

## Snowflake access

The local Snowflake CLI admin connection works. The [Phase 0 bootstrap SQL](../sql/phase0_bootstrap.sql) created the dedicated role, empty database/schemas/internal stage, and XS warehouse on 2026-09-29. Metadata checks confirmed the warehouse is suspended and the role has the intended grants. The named public key `QUAKEWATCH_KEY` is registered and restricted to `QUAKEWATCH_ROLE`; `snow connection test -c quakewatch_project` succeeded with the encrypted local private key. See the [Phase 0 environment check](environment.md) for evidence and remaining Phase 1/2 checks. Store authentication material outside Git. Do not paste private keys or passwords into chat or commit them.

## Phase 1 raw tables

The [raw-table SQL](../sql/phase1_raw_tables.sql) created `QUAKEWATCH.RAW.BATCH_ATTEMPT` and `QUAKEWATCH.RAW.RAW_EVENT_RECORDS` under `QUAKEWATCH_ROLE` on 2026-09-29. `DESCRIBE TABLE` confirmed 21 and 10 columns respectively, including the full-source `PAYLOAD VARIANT`. The first 15-row Seattle attempt was loaded on 2026-09-29; see [results](results.md). Repeat-run and wider history evidence remain pending.

The [RAW COPY mapping](../sql/phase1_copy_raw.sql) selects each JSONL record's capture metadata and full `source_feature`, plus Snowflake's staged filename and file row number. It ran for the first Seattle attempt. Its `attempt_id` template value names the unique stage directory containing that attempt's `events.jsonl`. Reconcile the COPY result and RAW row count against the completed manifest before recording a successful load.

Before staging, `validate_local_batch` checks that the manifest is complete, has no coverage gaps, and matches every local JSONL row and its count. After COPY, `reconcile_loaded_rows` requires both the COPY loaded-row count and the attempt-filtered RAW row count to equal that local count. The loader invokes both checks and appends a batch receipt after reconciliation.

To inspect the first upload plan without connecting to Snowflake, run `PYTHONPATH=src .venv/bin/python -m quakewatch.raw_load data/raw/20260929T075452Z-26375840ea/manifest.json`. It checks the local envelope and prints the attempt-specific stage path and expected row count. The generated PUT/COPY statements are prepared for the later loader; this command does not execute them.

The Python Connector boundary reads only `quakewatch_project` from the local Snowflake CLI config, verifies its key-pair authenticator and `QUAKEWATCH_ROLE`, and prompts for the encrypted key passphrase in the terminal when a live run is explicitly started. It never reads the admin profile or takes the passphrase from a command-line argument.

For read-only row checks, use this Python Connector boundary too. The installed Snowflake CLI `snow sql -c quakewatch_project` does not prompt for the encrypted key passphrase and fails unless that passphrase is supplied through CLI configuration or environment; do not place it in chat or shell history. The connector prompts privately in the terminal. The first independent check found one complete receipt and 15 RAW rows for the Seattle attempt.

The loader has an explicit `--execute` path. It checks for an existing attempt receipt or RAW rows, uploads one new file, runs the COPY mapping, compares COPY and attempt-filtered RAW counts with the local manifest, then appends a `BATCH_ATTEMPT` receipt. A COPY or count failure appends a failed receipt if the connection still permits it; a retry needs a new extraction attempt ID. The command without `--execute` remains read-only. Ask for warehouse-cost approval before each live run.
