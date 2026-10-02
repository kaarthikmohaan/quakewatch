# SQL

Reviewed Snowflake SQL for QuakeWatch, named by the phase that introduced it.
Each file's header comments describe its grain, owner, and cost or approval
notes. Anything that resumes the warehouse uses credits, so check the
[operations reference](../docs/operations-reference.md) before running it.

## Setup order

`make bootstrap EXECUTE=1` applies files 2 to 8 in this order using
[`scripts/pipeline/bootstrap.py`](../scripts/pipeline/bootstrap.py); file 1
needs an admin role and file 9 is created by `make quality` when absent.

| Order | File | Role | Creates |
|---|---|---|---|
| 1 | [`phase0_bootstrap.sql`](phase0_bootstrap.sql) | Admin, once | Project role, database, `RAW` and `CURATED` schemas, XS warehouse, internal stage |
| 2 | [`phase1_raw_tables.sql`](phase1_raw_tables.sql) | `QUAKEWATCH_ROLE` | `BATCH_ATTEMPT` and `RAW_EVENT_RECORDS` |
| 2a | [`phase1_update_watermark.sql`](phase1_update_watermark.sql) | `QUAKEWATCH_ROLE` | `UPDATE_WATERMARK`, the committed update-sweep watermark |
| 3 | [`phase2_staging_table.sql`](phase2_staging_table.sql) | `QUAKEWATCH_ROLE` | Typed staging table |
| 4 | [`phase2_process_attempt.sql`](phase2_process_attempt.sql) | `QUAKEWATCH_ROLE` | Transformation audit table |
| 5 | [`phase2_dimensions_bridge.sql`](phase2_dimensions_bridge.sql) | `QUAKEWATCH_ROLE` | Dimensions and the event-site bridge |
| 6 | [`phase2_revision_current.sql`](phase2_revision_current.sql) | `QUAKEWATCH_ROLE` | Revision fact and `EVENT_CURRENT` view |
| 7 | [`phase2_batch_fact.sql`](phase2_batch_fact.sql) | `QUAKEWATCH_ROLE` | Batch-run fact |
| 8 | [`phase2_create_procedure.sql`](phase2_create_procedure.sql) | `QUAKEWATCH_ROLE` | Snowpark procedure; upload the bundle from [`build_procedure_bundle.py`](../scripts/pipeline/build_procedure_bundle.py) first |
| 9 | [`phase3_health_views.sql`](phase3_health_views.sql) | `QUAKEWATCH_ROLE` | Batch-health, loaded-window, and reject views |

## Used during runs

| File | Used by | Purpose |
|---|---|---|
| [`phase1_copy_raw.sql`](phase1_copy_raw.sql) | RAW loader | `COPY INTO` mapping for one staged attempt |
| [`phase3_reconciliation.sql`](phase3_reconciliation.sql) | Quality checks | Receipt, RAW, staging, and processed-count reconciliation |
| [`phase3_uniqueness.sql`](phase3_uniqueness.sql) | Quality checks | Duplicate revision and bridge keys; each query should return zero rows |
| [`phase3_metrics.sql`](phase3_metrics.sql) | Latency check | First-backfill fetch-to-curated measurement against its predeclared target |
| [`phase3_sample_analysis.sql`](phase3_sample_analysis.sql) | Sample analysis | Bounded Seattle query over current events |

## Optional demos

| File | Purpose |
|---|---|
| [`phase2_fixture_setup.sql`](phase2_fixture_setup.sql) | Creates the separate fixture database used by Phase 2 and Phase 4 drills |
| [`phase4_recovery_preflight.sql`](phase4_recovery_preflight.sql) | Read-only check before the clone and Time Travel drill |
| [`phase4_cortex_aggregates.sql`](phase4_cortex_aggregates.sql) | Ten bounded site aggregates used as Cortex input |

The quality, uniqueness, and latency checks in
[`scripts/checks/`](../scripts/checks/) verify each SQL file's SHA-256 hash
before running it, so editing one of those files means updating its recorded
hash.
