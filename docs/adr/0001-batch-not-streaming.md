# ADR 0001: Batch extraction instead of streaming

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026

## Context

The USGS FDSN event API answers bounded queries, caps each response at 20,000 events, and offers no consistent snapshot of the catalog. Events are revised and deleted long after they occur. The project needs every loaded window to be auditable and replayable.

## Decision

Run bounded, manually invoked batches. Each batch has a stable logical ID, a unique attempt ID, a saved JSONL file, and a manifest recording request parameters and before/after counts. Snowpipe Streaming, Kafka, and similar infrastructure are out of scope.

## Consequences

- Every window can be reconciled and replayed from RAW without refetching.
- Freshness depends on how often batches run; there is no sub-minute path.
- The design does not claim complete coverage from a successful run.

**References:** [Design: batch architecture](../design.md#batch-architecture-and-roadmap)
