# ADR 0010: Live integration check compiles SQL instead of running the procedure

**Status:** Accepted · **Decided:** 2 October 2026 · **Recorded:** 2 October 2026

## Context

CI runs only offline tests. The Snowpark writers are tested with fake sessions,
so a renamed column or table in Snowflake would not fail CI; it would fail the
next live procedure call. Running the procedure in CI is not safe: it writes to
the warehouse and manages its own transactions, so a test cannot wrap it and
roll back.

## Decision

Add a read-only live check, `make integration EXECUTE=1`, and a manually
triggered GitHub workflow that runs it. It plans every SQL statement the
procedure issues, and every reviewed check and analysis query, with
`EXPLAIN USING TEXT`, substituting harmless values for bind markers. EXPLAIN
compiles a statement against the live tables without running it. The check
then confirms the deployed procedure exists and requires the read-only
post-run and uniqueness checks to pass. CI connects with key-pair settings from
four repository secrets; local runs keep the passphrase prompt.

## Consequences

- Schema drift between the code and Snowflake fails a cheap, read-only check.
- Runtime behaviour (MERGE results, transactions, rollbacks) is still proven
  only by the recorded live drills and offline tests.
- The workflow is manual, so it runs only when someone starts it.

**References:** [integration.py](../../scripts/checks/integration.py), [integration workflow](../../.github/workflows/integration.yml)
