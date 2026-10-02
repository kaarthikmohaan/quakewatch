# ADR 0008: Reject USGS stub records with their own reason

**Status:** Accepted · **Decided:** 2 October 2026 · **Recorded:** 2 October 2026

## Context

All 485 rejected rows were labelled `invalid_origin_time`. Investigation showed they are USGS placeholder features with no time, magnitude, or status, coordinates `[0, 0]`, and alias IDs pointing at full records that were loaded normally.

## Decision

In parser version 2, reject these as `source_stub_record`. Also reject an active record at the `[0, 0]` placeholder as `placeholder_location`, but keep a deleted record there as a tombstone without coordinates. Do not feed stub IDs into alias resolution, because the full records already carry the same links.

## Consequences

- Reject reasons describe causes, and the [reject analysis](../results.md#reject-analysis) documents the evidence.
- Rows already in Snowflake keep the version 1 label until reprocessed.
- The fixture procedure bundle hash changed and was updated.

**References:** [staging.py](../../src/quakewatch/staging.py)
