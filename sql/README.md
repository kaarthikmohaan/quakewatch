# SQL

Reviewed Snowflake SQL for QuakeWatch, grouped by purpose:

| Folder | Contents |
|---|---|
| [`setup/`](setup) | Object definitions, numbered in the order they must be applied |
| [`load/`](load) | The `COPY INTO` mapping used by the RAW loader |
| [`checks/`](checks) | Reconciliation, uniqueness, and latency queries |
| [`analysis/`](analysis) | Analytical queries over current events |
| [`demos/`](demos) | SQL for the isolated fixture database and recovery drill |

Each file's header comments describe its grain, owner, and cost or approval
notes. Anything that resumes the warehouse uses credits, so check the
[operations reference](../docs/operations-reference.md) before running it.

## Setup order

Apply the `setup/` files in number order. `01` needs an admin role and runs
once. `make bootstrap EXECUTE=1` applies `02` to `09` using
[`scripts/pipeline/bootstrap.py`](../scripts/pipeline/bootstrap.py), and
`make quality` creates the `10` views when they are absent.

| File | Role | Creates |
|---|---|---|
| [`setup/01_bootstrap_admin.sql`](setup/01_bootstrap_admin.sql) | Admin, once | Project role, database, `RAW` and `CURATED` schemas, XS warehouse, internal stage |
| [`setup/02_raw_tables.sql`](setup/02_raw_tables.sql) | `QUAKEWATCH_ROLE` | `BATCH_ATTEMPT` and `RAW_EVENT_RECORDS` |
| [`setup/03_update_watermark.sql`](setup/03_update_watermark.sql) | `QUAKEWATCH_ROLE` | `UPDATE_WATERMARK`, the committed update-sweep watermark |
| [`setup/04_staging_table.sql`](setup/04_staging_table.sql) | `QUAKEWATCH_ROLE` | Typed staging table |
| [`setup/05_process_attempt.sql`](setup/05_process_attempt.sql) | `QUAKEWATCH_ROLE` | Transformation audit table |
| [`setup/06_dimensions_bridge.sql`](setup/06_dimensions_bridge.sql) | `QUAKEWATCH_ROLE` | Dimensions and the event-site bridge |
| [`setup/07_revision_current.sql`](setup/07_revision_current.sql) | `QUAKEWATCH_ROLE` | Revision fact and `EVENT_CURRENT` view |
| [`setup/08_batch_fact.sql`](setup/08_batch_fact.sql) | `QUAKEWATCH_ROLE` | Batch-run fact |
| [`setup/09_create_procedure.sql`](setup/09_create_procedure.sql) | `QUAKEWATCH_ROLE` | Snowpark procedure; upload the bundle from [`build_procedure_bundle.py`](../scripts/pipeline/build_procedure_bundle.py) first |
| [`setup/10_health_views.sql`](setup/10_health_views.sql) | `QUAKEWATCH_ROLE` | Batch-health, loaded-window, and reject views |

## Used during runs

| File | Used by | Purpose |
|---|---|---|
| [`load/copy_raw.sql`](load/copy_raw.sql) | RAW loader | `COPY INTO` mapping for one staged attempt |
| [`checks/reconciliation.sql`](checks/reconciliation.sql) | Quality checks | Receipt, RAW, staging, and processed-count reconciliation |
| [`checks/uniqueness.sql`](checks/uniqueness.sql) | Quality checks | Duplicate revision and bridge keys; each query should return zero rows |
| [`checks/latency_metrics.sql`](checks/latency_metrics.sql) | Latency check | First-backfill fetch-to-curated measurement against its predeclared target |
| [`analysis/sample_seattle_day.sql`](analysis/sample_seattle_day.sql) | Sample analysis | Bounded Seattle query over current events |

## Optional demos

| File | Purpose |
|---|---|
| [`demos/fixture_setup.sql`](demos/fixture_setup.sql) | Creates the separate fixture database used by Phase 2 and Phase 4 drills |
| [`demos/recovery_preflight.sql`](demos/recovery_preflight.sql) | Read-only check before the clone and Time Travel drill |
| [`analysis/site_year_aggregates.sql`](analysis/site_year_aggregates.sql) | Ten bounded site aggregates used as Cortex input |

The quality, uniqueness, and latency checks in
[`scripts/checks/`](../scripts/checks) verify each SQL file's SHA-256 hash
before running it, so editing one of those files means updating its recorded
hash.
