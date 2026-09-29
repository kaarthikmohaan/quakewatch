# Runbook

## Local setup

1. Install Python 3.12 and `uv`.
2. From the repository root, run `uv sync --locked --no-editable`.
3. Run a small, explicit time range before requesting a multi-year history.

The non-editable install is used because the editable-package path was not loading correctly in this local environment. After changing package code, run `uv sync --locked --no-editable --reinstall-package quakewatch` to rebuild the installed wheel; a plain `uv sync` can report everything checked while leaving an older wheel installed.

## Fetch a bounded batch

```sh
uv run quakewatch-extract \
  --site seattle \
  --start 2026-09-28T00:00:00Z \
  --end 2026-09-29T00:00:00Z
```

Supported public demo sites are `seattle`, `san-francisco`, and `anchorage`. Times without an explicit zone are interpreted as UTC. Output goes to `data/raw/<attempt-id>/` unless `--output` is provided. Keep private coordinates and credentials out of the repository.

## Inspect a run

Read `manifest.json` first. A successful manifest has status `complete`; each leaf query window should show matching `count_before`, `returned_rows`, and `count_after`. A failed run writes a failed manifest for investigation and retry. At present, a failure inside `fetch_window` leaves `window_audit` empty; use its error text and requested range to identify the gap until structured unresolved-window auditing is implemented in Phase 1. The source is not a durable event log, and a successful response does not prove gap-free catalog coverage.

## Snowflake access

The local Snowflake CLI admin connection works. The [Phase 0 bootstrap SQL](../sql/phase0_bootstrap.sql) created the dedicated role, empty database/schemas/internal stage, and XS warehouse on 2026-09-29. Metadata checks confirmed the warehouse is suspended and the role has the intended grants. The named public key `QUAKEWATCH_KEY` is registered and restricted to `QUAKEWATCH_ROLE`; `snow connection test -c quakewatch_project` succeeded with the encrypted local private key. See the [Phase 0 environment check](environment.md) for evidence and remaining Phase 1/2 checks. Store authentication material outside Git. Do not paste private keys or passwords into chat or commit them.

## Phase 1 raw tables

The [raw-table SQL](../sql/phase1_raw_tables.sql) created `QUAKEWATCH.RAW.BATCH_ATTEMPT` and `QUAKEWATCH.RAW.RAW_EVENT_RECORDS` under `QUAKEWATCH_ROLE` on 2026-09-29. `DESCRIBE TABLE` confirmed 21 and 10 columns respectively, including the full-source `PAYLOAD VARIANT`. The warehouse was still suspended after this metadata check. The tables are empty until the stage/upload/COPY path is implemented; do not treat their existence as a successful raw load.
