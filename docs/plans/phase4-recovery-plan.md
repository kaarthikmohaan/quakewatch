# Phase 4 sandbox recovery plan

This is a plan for the optional clone and Time Travel demonstration in
[`design.md`](../design.md). No Phase 4 Snowflake recovery operation has been run.
The already verified RAW retry and failed-transform evidence is recorded in
[`results.md`](../results.md); that evidence is separate from this drill.

## Boundary and approval

- Use only `QUAKEWATCH_PHASE2_FIXTURE`, never the main `QUAKEWATCH` database.
- Clone only `CURATED.FACT_EVENT_REVISION` into a uniquely named sandbox table.
  Before running, check that the destination name is absent and that the source
  has the expected fixture row count. Stop on any unexpected state.
- The warehouse should be XS with auto-suspend. Queries, the clone, mutation,
  and Time Travel verification can consume warehouse credits. A zero-copy clone
  begins without copied table storage, but changed data and retained history can
  increase storage. Confirm the account edition and current retention before
  promising a recovery window. Record actual query IDs and credits if the
  account usage views make them available.
- Get explicit approval for warehouse cost, creating the clone,
  and deliberately mutating **only the clone**. Get separate approval before
  dropping the clone; no project source table or data is to be deleted.
- Do not run Cortex as part of this recovery drill.

## Proposed sequence

1. **Read-only preflight.** Check the project role, active warehouse, fixture
   source table and row count, absence of the intended clone name, account
   edition, and table Time Travel retention. Save the query IDs and timestamp.
   The reviewed statements are in
   [`sql/phase4_recovery_preflight.sql`](../../sql/phase4_recovery_preflight.sql).
   The matching [Python runner](../../scripts/evidence/phase4/phase4_recovery_preflight.py) prompts
   locally for the encrypted project key; its default mode is offline preview,
   and `--execute` runs only after warehouse-cost approval.
   Based on the latest documented fixture snapshot, expect one five-row source
   fact table, no `QW_PHASE4_REVISION_DEMO` table, at least one day of
   retention, and no duplicate logical revision keys. A mismatch stops the
   drill for inspection; it is not repaired by overwriting a table.
2. **Clone isolation.** Create a table clone of fixture
   `CURATED.FACT_EVENT_REVISION`. Compare source and clone counts and the
   selected logical key/value. Change that fixture row in the clone. Verify the
   source still has its original value and count while the clone changed.
   The [guarded runner](../../scripts/evidence/phase4/phase4_clone_recovery.py) uses the five-row
   preflight, a new table name without overwrite syntax, and a one-row
   clone-only `MERGE`. Its default command is an offline preview.
3. **Time Travel.** Suspend all writers to the fixture clone. Capture the inner
   `MERGE` statement query ID for a deliberate bad change to that clone. Query
   the clone `BEFORE (STATEMENT => '<query-id>')` and compare with its current
   state. Capture before/after counts and the affected key/value. If a recovery
   clone is created from the pre-merge state, check it against that snapshot.
4. **Raw recovery cross-check.** Point to the existing first-ever transform
   failure and retry evidence: the same durable RAW row was processed without
   refetch, the failure audit persisted, logical revision/bridge counts stayed
   stable, and duplicate-key groups were zero. Do not rerun its one-shot drill.
5. **Record and clean up.** Add observed query IDs, counts, retention, actual
   usage data or an explicit measurement gap, and limitations to `results.md`.
   After separate deletion approval, drop only the demo clone and any recovery
   clone. Report if cleanup is deferred.
   The [guarded cleanup runner](../../scripts/evidence/phase4/phase4_clone_cleanup.py) checks the
   recorded five-row source/clone and changed magnitude before dropping the
   fixed demo-clone name. It does not drop the fixture source or database.

## Pass condition and limits

The source table remains unchanged after the clone mutation; the statement-ID
Time Travel read returns the pre-merge clone state; and the captured evidence
is sufficient to reproduce each comparison within the account's retention
window. This would demonstrate sandbox recovery only. It would not close the
three unresolved USGS history windows, complete the catalog-wide update
sweep, prove production recovery, or erase the missed Phase 3 latency target.
