# Results

## First live source capture

| Measure | Observed value |
|---|---|
| Site | Seattle public example point, 250 km radius |
| Requested range | 2026-09-28 00:00 UTC through 2026-09-29 00:00 UTC |
| Count before fetch | 15 |
| Features returned | 15 |
| Count after fetch | 15 |
| Raw JSON Lines written | 15 |
| Window result | Reconciled |
| Snowflake rows loaded | Not yet implemented |

This is one source-capture observation, not a completeness guarantee or a performance claim. The local manifest and source rows are under ignored `data/raw/` and are not published to GitHub.

## Not measured yet

- Repeat-batch idempotency and revision/tombstone behavior
- Snowflake fetch-to-curated latency, rejects, and pending batches
- FDSN update-sweep coverage gaps
- Warehouse credit usage
- User task completion time or usefulness
