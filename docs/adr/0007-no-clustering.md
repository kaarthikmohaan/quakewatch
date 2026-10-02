# ADR 0007: No clustering or special partitioning at this volume

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026

## Context

The warehouse holds about 216,000 source observations. Clustering keys and search optimisation add maintenance cost.

## Decision

Do not add clustering or special partitioning without query-profile evidence. Use an X-Small warehouse with 60-second auto-suspend.

## Consequences

- Measured costs stay small: 0.0039 AI credits for 11 Cortex calls and a shared-hour warehouse snapshot.
- The project does not demonstrate tuning at scale.

**References:** [Design: warehouse model](../design.md#warehouse-model-and-ownership), [bootstrap SQL](../../sql/phase0_bootstrap.sql)
