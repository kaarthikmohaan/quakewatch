# ADR 0006: Command-driven orchestration without Airflow

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026

## Context

The pipeline is a short chain in one warehouse: extract, upload, `COPY INTO`, reconcile, and call one procedure.

## Decision

Use the Python commands as the only orchestrator for the MVP. Do not add Airflow for this graph; Snowflake Tasks are post-MVP and would not start the local extractor.

## Consequences

- Few moving parts, and every step can be previewed without cost.
- There is no schedule, alerting, or steady-state latency; the first backfill missed its latency target partly because curation ran manually.
- Scheduling is the main next step listed in the README.

**References:** [Design: orchestration](../design.md#orchestration-observability-and-recovery)
