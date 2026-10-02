# ADR 0005: One writer per table and one transaction per batch

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026

## Context

A transformation can fail halfway through writing several tables. Retrying must not duplicate facts or erase the record of the earlier failure.

## Decision

The Python runner and `COPY INTO` own RAW and its receipts. A Snowpark procedure owns staging, facts, dimensions, and the processing log. Model writes and the success record commit in one transaction; on failure the procedure rolls back and appends a separate failure record. DDL stays outside the transaction.

## Consequences

- A failed transform is retried from RAW without refetching, verified in two Snowflake drills.
- An uncertain `COMMIT` stops for manual inspection instead of guessing.
- Processing runs inside Snowflake, so the procedure depends on the account's Snowpark runtime.

**References:** [process_transaction.py](../../src/quakewatch/process_transaction.py)
