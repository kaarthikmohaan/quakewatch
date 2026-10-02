# Phase 2 first Snowflake pilot plan

Prepared and executed 2026-09-30. The plan below describes the bounded first run; [results](../results.md) record the measured outcome.

## Scope and preflight

The first pilot uses only loaded Seattle attempt `20260929T075452Z-26375840ea`. Its local manifest is complete, with 15 returned/written rows and zero coverage gaps. A prior Snowflake read found one complete receipt and 15 RAW rows; the pilot checks those facts again live before writing. It also requires the `QUAKEWATCH.CURATED` schema to have no existing tables, views, or procedures. If it is not empty, stop and inspect its objects instead of applying `IF NOT EXISTS` over an unknown shape.

The local command is `PYTHONPATH=src .venv/bin/python scripts/evidence/phase2/phase2_pilot.py`. Without `--execute`, it only prints the plan and does not connect. The live form adds `--execute` and prompts for the existing encrypted project key passphrase outside Git and chat. Do not run live until the warehouse cost has been approved. The procedure includes conditional duplicate-row deletion; the empty-schema guard means this **first** pilot has no pre-existing curated fact/bridge rows to delete. Any later replay or broader run needs a separate deletion review before it executes.

## Exact live sequence

1. Connect as `QUAKEWATCH_ROLE`, use `QUAKEWATCH_WH`, and set a 300-second statement timeout.
2. Check for an empty curated schema. Check one complete, gap-free load receipt and exactly 15 attempt-filtered RAW rows.
3. Upload the ignored 24 KB local `data/procedure/quakewatch_procedure.zip` to `@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure/` with `OVERWRITE=FALSE`. Stop if Snowflake does not report `UPLOADED`.
4. Apply the committed local DDL in this order: typed staging, process-attempt log, dimensions/bridge, revision fact/current view, batch fact, and procedure definition. The definition pins Python 3.12 and `snowflake-snowpark-python==1.55.0`, which appeared in the account catalog on 2026-09-29. Recheck if registration rejects that package.
5. Call `QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT` once for the 15-row attempt. A complete result must report 15 loaded and processed rows. The procedure records success with model writes in one transaction; on a transform failure it rolls those writes back and records a failed processing attempt separately.
6. Read curated counts. Require 15 staged rows, at most 15 distinct revision rows, three bridge rows per revision, one batch fact, one process-attempt row, and three public site rows. Stop after this one attempt. Do not start the 177-attempt history run automatically.

The runnable code for this sequence is [scripts/evidence/phase2/phase2_pilot.py](../../scripts/evidence/phase2/phase2_pilot.py). The local test checks its preview, SQL statement splitting, and preflight stops. Snowflake SQL behavior still requires the live pilot to verify.

## Expected cost and limits

The project warehouse was configured X-Small with 60-second auto-suspend and auto-resume. Snowflake lists a **Gen1 X-Small standard warehouse at 1 credit/hour**, billed per second with a **60-second minimum each time it starts**. That is about **0.017 credit minimum**; a continuously running 2–6 minute pilot, including idle time before auto-suspend, would be about **0.033–0.100 credits**. This is a scenario, not a cap or bill forecast. Procedure compilation or a failing query can extend runtime. The account's dollar price per credit, warehouse generation, other service charges, and storage price have not been verified. Stage storage for the 24 KB ZIP and small curated tables is expected to be small but is not measured. [Snowflake warehouse billing](https://docs.snowflake.com/en/user-guide/warehouses-overview), [warehouse considerations](https://docs.snowflake.com/en/user-guide/warehouses-considerations).

The live pilot subsequently completed one procedure call and the expected count checks: 15 staged rows, 15 revisions, 45 bridge rows, one batch fact, one processing attempt, and three public sites. The initial curated schema was empty, so there were no pre-existing curated rows to delete. Actual credits remain unmeasured. No GitHub push was performed.
