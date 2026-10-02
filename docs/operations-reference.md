# Operations reference

How to run every QuakeWatch command, what each one checks, and which ones must
not be rerun. Measured results are in the [results summary](results.md) and the
dated [evidence log](evidence/results-log.md). Check current account and source
state before running anything that connects to Snowflake or USGS.

Most commands below have a `make` target (`make help` lists them). Commands that
reach USGS or Snowflake preview by default and act only with `--execute` (or
`EXECUTE=1` for `make`). Every Snowflake run uses warehouse credits.

## Local setup

1. Install Python 3.12 and `uv`.
2. From the repository root, run `uv sync --locked --no-editable`.
3. Run a small, explicit time range before requesting a multi-year history.

The non-editable install is used because the editable-package path did not load
correctly in this local environment. After changing package code, run
`uv sync --locked --no-editable --reinstall-package quakewatch`; a plain
`uv sync` can report everything checked while leaving an older wheel installed.

Installing the Snowflake Python Connector does not connect to Snowflake or start
warehouse compute.

## Fetch a bounded batch

```sh
.venv/bin/quakewatch-extract \
  --site seattle \
  --start 2026-09-28T00:00:00Z \
  --end 2026-09-29T00:00:00Z
```

Supported public demo sites are `seattle`, `san-francisco`, and `anchorage`.
Times without an explicit zone are UTC. Output goes to `data/raw/<attempt-id>/`
unless `--output` is provided. Keep private coordinates and credentials out of
the repository. This command fetches immediately; it has no preview mode.

## Capture the five-year history

`PYTHONPATH=src .venv/bin/python -m quakewatch.history_plan --cutoff 2026-09-29T00:00:00Z`
prints 60 contiguous month-sized windows per public site (180 in total) without
contacting USGS or Snowflake (`make plan-history`). Month-sized windows replaced
year-sized ones after a year-long count request timed out.

| Option | Effect |
|---|---|
| `--resume-preview` | Shows the first month without a complete local manifest and event file. Local inventory only; failed manifests stay visible and are not counted as complete. |
| `--resume --max-windows N` | Previews a run of up to N windows (1–50); add `--execute` to contact USGS (`make capture-history`). Stops at the first failed manifest and reports its path. Does not load Snowflake. |
| `--start-window N` | With `--resume`, continues from a later month. Skipped windows stay uncaptured and visible; the history must be reported as incomplete until they reconcile. |
| `--window N` | Previews one window; with `--execute`, fetches just that window. `--execute` without `--window` or `--resume` is refused, so the full history cannot start by accident. |
| `--source-days 7` or `1` | Starts a slow month as contiguous child requests of at most that many days. Every child must reconcile before the month is complete; a failed child writes no partial file. |
| `--resume-children` | Saves each reconciled child under `data/raw/<attempt-id>/children/` and reuses a checkpoint only when its logical batch, slice size, query parameters, content hash, and counts all match. Reused rows keep their original fetch time. |
| `--source-hours 3 --hourly-child N` | With `--source-days 1 --resume-children`, splits only daily child N (1-based, from the failed manifest) into three-hour requests, each with its own checkpoint. |

How the extractor protects coverage:

- It targets fewer than 10,000 features per leaf request, below the USGS
  20,000-result limit, and splits a window at a count of 10,000 or more before
  fetching features.
- Repeated timeouts split a window into smaller audited requests, up to three
  timeout split levels. Consecutive HTTP read timeouts are capped at two; other
  temporary errors and retryable statuses at four attempts.
- Each source window has a 180-second wall-clock budget shared by its retries
  and splits. When it expires, or the command is interrupted or terminated, the
  attempt is marked `failed` with zero written rows and an explicit gap.
- The manifest records `active_window` and saves each completed child audit
  before the next begins, so a failed manifest shows exactly which child failed.
- A combined month is best-effort reconciliation across fetch times, not a
  transactionally consistent USGS snapshot; the update sweep must still detect
  later changes.

## Inspect a run

Read `manifest.json` first. A successful manifest has status `complete`, and
each leaf window shows matching `count_before`, `returned_rows`, and
`count_after`. A failed window appears in `coverage_gaps` with its ID, bounds,
and reason; `window_audit` also keeps parent splits and earlier siblings. A
failed run writes no event file. A successful response does not prove gap-free
catalog coverage.

## Snowflake access

Commands read the `quakewatch_project` profile from `~/.snowflake/config.toml`
(see [`snowflake-config.example.toml`](../snowflake-config.example.toml)),
require key-pair authentication and `QUAKEWATCH_ROLE`, and prompt for the
encrypted key passphrase in the terminal. They never read the admin profile or
take the passphrase from a command-line argument. The key is restricted to
`QUAKEWATCH_ROLE`. Store authentication material outside Git and never paste it
into chat.

In CI, the same commands read four `QUAKEWATCH_SNOWFLAKE_*` environment
variables instead; see [CONTRIBUTING](../CONTRIBUTING.md#live-integration-check).

The admin profile is used only for the one-time
[bootstrap SQL](../sql/setup/01_bootstrap_admin.sql) and the read-only
account-usage metering script. The Snowflake CLI `snow sql -c quakewatch_project`
does not prompt for the key passphrase, so use the Python commands for
project-role queries. See the [Phase 0 environment check](evidence/phase0-environment-check.md).

## Create the Snowflake objects

Apply [`sql/setup/`](../sql/README.md) in number order: `01` once with an admin
role, then `make bootstrap EXECUTE=1` for the project tables and procedure, and
`make quality EXECUTE=1` to create the health views when absent. The procedure
bundle is built offline with
`PYTHONPATH=src .venv/bin/python scripts/pipeline/build_procedure_bundle.py`,
which writes the ignored `data/procedure/quakewatch_procedure.zip` and prints its
SHA-256; the [procedure definition](../sql/setup/09_create_procedure.sql) expects
it at `@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure/quakewatch_procedure.zip`.

## Load RAW

- **Inventory:** `PYTHONPATH=src .venv/bin/python -m quakewatch.history_load_plan --cutoff 2026-09-29T00:00:00Z`
  prints one candidate attempt and expected row count per captured window. It
  makes no Snowflake connection, so already loaded attempts may appear. Add
  `--check-snowflake` to label each candidate `loaded` (one complete receipt and
  matching receipt, RAW, and local counts), `ready` (no receipt and no RAW
  rows), or `investigate` (anything else, which must not be bulk loaded). This is
  SELECT only.
- **Bulk load:** `PYTHONPATH=src .venv/bin/python -m quakewatch.history_raw_load --cutoff 2026-09-29T00:00:00Z --max-windows 50`
  validates local candidates (`make load-history`); with `--execute` it loads at
  most 1–50 `ready` attempts in window order, rechecking each immediately before
  PUT and COPY and stopping on any `investigate` state or load error. Rerunning
  skips attempts with matching complete receipts.
- **One batch:** `PYTHONPATH=src .venv/bin/python -m quakewatch.raw_load <manifest>`
  prints the expected row count and stage path (`make load-preview`); with
  `--execute` it refuses an attempt that already has a receipt or RAW rows,
  uploads one file, runs the [COPY mapping](../sql/load/copy_raw.sql), compares
  COPY and attempt-filtered RAW counts with the manifest, and appends a
  `BATCH_ATTEMPT` receipt. A failure appends a failed receipt when the connection
  allows; a retry needs a new extraction attempt ID. The COPY mapping selects each
  record's capture metadata and full `source_feature`, plus Snowflake's staged
  filename and row number; its `attempt_id` value names the attempt's unique
  stage directory.

Before staging, `validate_local_batch` requires a complete manifest with no
coverage gaps whose JSONL rows match its count; after COPY,
`reconcile_loaded_rows` requires both the COPY count and the attempt-filtered RAW
count to equal it. Incomplete, failed, or terminated attempts are refused.

## Process loaded attempts

`PYTHONPATH=src:. .venv/bin/python scripts/pipeline/process_history.py --max-attempts 5`
previews (`make process`). With `--execute` it selects at most 1–200 pending
origin attempts, checks each RAW and receipt count before its procedure call,
requires a reconciled health row afterwards, prints progress per attempt, and
stops on the first mismatch. Each call uses warehouse compute, and the
procedure's alias-collision handler can delete curated rows, so check the cost
first.

## Quality checks

All read-only. Each previews without connecting and runs with `--execute`.

| Command | What it checks |
|---|---|
| [`checks/quality.py`](../scripts/checks/quality.py) (`make quality`) | Hashes the three reviewed SQL files; creates the [health views](../sql/setup/10_health_views.sql) only when all are absent, or reuses them when the stored definitions match byte for byte; reports health and anomaly counts and runs the Seattle sample. It never deletes or replaces a view; after a partial DDL failure, inspect before retrying. |
| [`checks/view_state.py`](../scripts/checks/view_state.py) | Prints the stored view definitions and their hashes. |
| [`checks/uniqueness.py`](../scripts/checks/uniqueness.py) (`make uniqueness`) | Duplicate revision and bridge keys from the [reviewed SQL](../sql/checks/uniqueness.sql); every query should return zero rows. |
| [`checks/postrun.py`](../scripts/checks/postrun.py) (`make postrun`) | Checks the view definitions, summarises batch health, counts loaded-window anomalies and duplicate keys, and groups rejects by reason. `pass` requires every receipt reconciled, zero anomalies and duplicates, and grouped rejects matching the health total. |
| [`checks/latency_metrics.py`](../scripts/checks/latency_metrics.py) (`make metrics`) | Fetch-to-curated distribution and fetch and source ages from the [metrics SQL](../sql/checks/latency_metrics.sql), whose sample and 24-hour p95 target were fixed before the first measurement. |
| [`checks/analysis.py`](../scripts/checks/analysis.py) (`make analysis`) | Runs the site-by-year and [Seattle-day](../sql/analysis/sample_seattle_day.sql) queries and prints the rows without saving them. |
| [`checks/integration.py`](../scripts/checks/integration.py) (`make integration`) | Compiles every SQL statement the procedure issues, and every reviewed check and analysis query, against the live schema with `EXPLAIN USING TEXT`; confirms the procedure exists; runs the post-run and uniqueness checks. Also runs from the manual **Snowflake integration** workflow ([ADR 0010](adr/0010-live-integration-check.md)). |

`PROCESSED_ROWS` includes rejected projections, so a complete attempt expects
`PROCESSED_ROWS = LOADED_ROWS` and checks the reject count separately. A loaded
attempt without a process audit is `PENDING_PROCESS`, not a count mismatch. The
views cannot see local source attempts that were never loaded; those gaps stay
in the local manifests.

The [CI workflow](../.github/workflows/ci.yml) runs the locked install, lint,
format and type checks, builds the deterministic synthetic fixtures, and runs the
tests under coverage on Python 3.12. It never connects to Snowflake.

## Update sweep

**Plan.** `PYTHONPATH=src .venv/bin/python -m quakewatch.update_plan` prints a
local plan from five required inputs: the catalog origin-time lower bound, a
fixed origin-time cutoff, the prior committed watermark, the sweep start, and a
positive overlap in seconds. `updatedafter` is the prior watermark minus the
overlap, with no spatial or magnitude filters; the proposed next watermark is the
sweep start. Example, with illustrative inputs only:

```bash
PYTHONPATH=src .venv/bin/python -m quakewatch.update_plan \
  --catalog-start 1900-01-01T00:00:00Z \
  --cutoff 2026-09-30T00:00:00Z \
  --last-watermark 2026-09-29T00:00:00Z \
  --sweep-started-at 2026-09-30T00:00:00Z \
  --overlap-seconds 86400
```

Expect `status: preview`, `updatedafter: 2026-09-28T00:00:00.000Z`, and
`watermark_advanced: false`. The first live sweep needs an explicit bootstrap
watermark and catalog lower bound; see the
[evidence log](evidence/results-log.md#first-update-sweep-bootstrap-preparation).
See the [USGS parameter contract](https://earthquake.usgs.gov/fdsnws/event/1/)
for origin time versus update time.

**Extract.** `PYTHONPATH=src .venv/bin/python -m quakewatch.update_extract`
takes the same five inputs and only prints the plan unless `--execute` is added.
It splits origin-time windows by counts, keeps the same `updatedafter` on every
child, includes deletions, reconciles every leaf, and bounds the whole attempt
with one three-minute deadline. Each run writes a unique manifest under
`data/raw/` with `batch_kind: update_sweep`; only a complete extraction publishes
`events.jsonl`, and extraction never advances the watermark: the manifest's
`last_committed_watermark` stays as planned and `watermark_advanced` stays
`false`. History loading commands exclude sweep attempts.

| Option | Effect |
|---|---|
| `--years-per-window N` (1–100) | Initial origin-time slice size; default 50 years |
| `--recent-start-year 2001 --recent-years-per-window 5` | Smaller slices for recent, denser years; with a year-0001 lower bound and a 2026 cutoff this makes 46 contiguous windows |
| `--monthly-start-year 2023 --recent-months-per-window 1` | Month-sized slices from that year onward |
| `--daily-month 2023-10` | One-day initial windows for a single slow month |
| `--resume-children` | Reuses a saved child only when its window ID, query parameters, checksum, row counts, and frozen sweep start all match; keep the same cutoff, sweep start, lower bound, prior watermark, and overlap on retries |

**Load and commit.** `PYTHONPATH=src .venv/bin/python -m quakewatch.update_load <sweep-manifest>`
validates a completed sweep locally. With `--execute` (and, for the first commit,
`--initial-watermark` matching the chosen bootstrap) it checks contiguous
coverage, every leaf's counts, and local rows per window; checks the prior
committed watermark; loads the attempt or recognises an earlier load; compares
the stored receipt manifest and per-window RAW counts; and only then advances
`QUAKEWATCH.RAW.UPDATE_WATERMARK` ([DDL](../sql/setup/03_update_watermark.sql))
by compare-and-set inside a transaction (`WHERE COMMITTED_WATERMARK = <previous>`), so two runners cannot both advance it
([ADR 0004](adr/0004-watermark-after-reconciliation.md)). If loading fails or
counts disagree, the watermark is unchanged; if the commit itself fails, rerunning
the same attempt completes it without another COPY. A stale sweep, a changed
lower bound, or a backward cutoff is rejected.

Offline verification of the sweep path:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_update_extract tests.test_update_plan \
  tests.test_extract_batch tests.test_raw_load -q
```

## One-shot evidence drills

These scripts produced the recorded Phase 2 and Phase 4 evidence. Each previews
offline with `PYTHONPATH=src:. .venv/bin/python <script>` and acts only with
`--execute`. Most guard against a second run; **do not rerun them** to present
the project. Use their recorded results in the evidence log instead.

| Script | Purpose and guard |
|---|---|
| [`evidence/phase2/pilot.py`](../scripts/evidence/phase2/pilot.py) ([plan](plans/phase2-pilot-plan.md)) | First procedure deployment and one call for the 15-row Seattle attempt; stops unless the curated schema is empty |
| [`evidence/phase2/rerun_check.py`](../scripts/evidence/phase2/rerun_check.py) ([plan](plans/phase2-rerun-plan.md)) | Same-attempt idempotency rerun; guarded by the first-pilot state |
| [`evidence/phase2/current_fixture.py`](../scripts/evidence/phase2/current_fixture.py) ([plan](plans/phase2-current-fixture-plan.md)) | Current-view logic on a session-only table; writes no permanent rows |
| [`fixtures/phase2_fixture_namespace.py`](../scripts/fixtures/phase2_fixture_namespace.py), [`fixtures/build_phase2_fixture_bundle.py`](../scripts/fixtures/build_phase2_fixture_bundle.py) | Offline: validate the fixture namespace and build the test-only ZIP and SQL ([plan](plans/phase2-procedure-fixture-plan.md)) |
| [`evidence/phase2/fixture_name_check.py`](../scripts/evidence/phase2/fixture_name_check.py) | Metadata-only check that the fixture database name is free (admin profile) |
| [`evidence/phase2/fixture_setup.py`](../scripts/evidence/phase2/fixture_setup.py) | Creates the fixture database from the [reviewed SQL](../sql/demos/fixture_setup.sql) (12 statements); stops on a name collision |
| [`evidence/phase2/fixture_deploy.py`](../scripts/evidence/phase2/fixture_deploy.py) | Deploys fixture objects after checking the pinned ZIP hash; stops unless the schemas are empty |
| [`fixtures/build_phase2_fixture_attempts.py`](../scripts/fixtures/build_phase2_fixture_attempts.py), [`evidence/phase2/fixture_raw_load.py`](../scripts/evidence/phase2/fixture_raw_load.py) | Builds and loads four synthetic one-row attempts; the loader stops unless the fixture tables are empty |
| [`evidence/phase2/fixture_original.py`](../scripts/evidence/phase2/fixture_original.py), [`fixture_update.py`](../scripts/evidence/phase2/fixture_update.py), [`fixture_deletion.py`](../scripts/evidence/phase2/fixture_deletion.py), [`fixture_stale_replay.py`](../scripts/evidence/phase2/fixture_stale_replay.py) | Process the original, later update, tombstone, and stale replay in order; each requires the exact state left by the previous step |
| [`fixtures/build_phase2_old_origin_attempts.py`](../scripts/fixtures/build_phase2_old_origin_attempts.py), [`evidence/phase2/old_origin_raw_load.py`](../scripts/evidence/phase2/old_origin_raw_load.py) | Builds and loads two synthetic 2020-origin attempts; guarded by an exact baseline |
| [`evidence/phase2/old_origin_original.py`](../scripts/evidence/phase2/old_origin_original.py), [`old_origin_pair.py`](../scripts/evidence/phase2/old_origin_pair.py), [`old_origin_update.py`](../scripts/evidence/phase2/old_origin_update.py) | Process the old-origin original and update. If the original succeeds and the update fails, do not rerun the pair; use the update-only guard after investigating |
| [`evidence/phase2/old_origin_state.py`](../scripts/evidence/phase2/old_origin_state.py), [`old_origin_final_check.py`](../scripts/evidence/phase2/old_origin_final_check.py) | Read-only state diagnostic and final check of the old-origin history, current view, counts, and keys |
| [`evidence/phase2/recovery_demo.py`](../scripts/evidence/phase2/recovery_demo.py) | Failed transform and retry for an already processed fixture batch, using a test-only failure procedure |
| [`evidence/phase2/first_failure_demo.py`](../scripts/evidence/phase2/first_failure_demo.py), [`first_failure_state.py`](../scripts/evidence/phase2/first_failure_state.py) | First-ever failure of a newly loaded synthetic batch, then a read-only state diagnostic |
| [`evidence/phase4/recovery_preflight.py`](../scripts/evidence/phase4/recovery_preflight.py) ([plan](plans/phase4-recovery-plan.md)) | Read-only preflight for the clone drill |
| [`evidence/phase4/clone_recovery.py`](../scripts/evidence/phase4/clone_recovery.py), [`clone_cleanup.py`](../scripts/evidence/phase4/clone_cleanup.py) | Clone and Time Travel drill on the fixture table, then drop of the demo clone. Never run the clone DDL against the main `QUAKEWATCH` database |
| [`checks/usage.py`](../scripts/checks/usage.py) | Read-only account-usage metering with the admin profile |
| [`evidence/live_demo_2026_10_02/`](../scripts/evidence/live_demo_2026_10_02) | Fixed-input drivers for the 2 October live demo; the core driver accepts a manifest path |

The isolated fixture database `QUAKEWATCH_PHASE2_FIXTURE` is kept until it is
deliberately cleaned up.

## Migrations

`make release-parser-v2` previews the
[parser version 2 release](../scripts/migrations/parser_v2.py). It has already
run; a rerun detects the migrated state and skips the data change.
