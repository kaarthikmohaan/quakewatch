# ADR 0004: Update watermark advances only after reconciliation

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026; storage changed 2 October 2026

## Context

The update sweep uses `updatedafter` to find revisions and deletions to old events. If the watermark advanced after a partial sweep, changes in the missing windows would be skipped silently.

## Decision

Advance the committed watermark to the sweep start time only after every window's before, returned, and after counts agree and the RAW receipt and per-window row counts match. On 2 October 2026 the watermark moved from a local JSON file with a single-host lock to the Snowflake table `RAW.UPDATE_WATERMARK`, advanced by a compare-and-set `UPDATE` in a transaction.

## Consequences

- An incomplete sweep stays retryable; the watermark has correctly not advanced while the live sweep is incomplete.
- Any machine or scheduler can run the loader, and a concurrent runner cannot double-advance the watermark.
- The table was created in Snowflake on 2 October 2026; no watermark has been committed yet.

**References:** [update_load.py](../../src/quakewatch/update_load.py), [watermark DDL](../../sql/setup/03_update_watermark.sql)
