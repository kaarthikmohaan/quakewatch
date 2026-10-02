"""Run one already captured QuakeWatch batch through Snowflake for a live demo."""

import json
from contextlib import closing
from pathlib import Path

from quakewatch.raw_load import connect_project, execute_raw_load, plan_raw_load

MANIFEST = Path("data/raw/20261002T045249Z-ee3a351be3/manifest.json")
STATE_SQL = """
SELECT HEALTH_STATUS, LOADED_ROWS, RAW_ROWS, STAGING_ROWS,
       PROCESSED_ROWS, REJECTED_ROWS
FROM QUAKEWATCH.CURATED.V_BATCH_HEALTH
WHERE ATTEMPT_ID = %s
"""


def show(label, value):
    print(json.dumps({label: value}, default=str, sort_keys=True), flush=True)


def main():
    plan = plan_raw_load(MANIFEST)
    attempt_id = plan["attempt_id"]
    show("local_batch", {"attempt_id": attempt_id, "rows": plan["expected_rows"]})
    with closing(connect_project()) as connection:
        with closing(connection.cursor()) as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("Unexpected Snowflake role or warehouse")

            cursor.execute(
                "SELECT COUNT(*) FROM QUAKEWATCH.RAW.BATCH_ATTEMPT WHERE ATTEMPT_ID = %s",
                (attempt_id,),
            )
            receipt_count = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS WHERE ATTEMPT_ID = %s",
                (attempt_id,),
            )
            raw_count = int(cursor.fetchone()[0])
            if receipt_count == raw_count == 0:
                loaded = execute_raw_load(plan, connection)
                show("raw_load", {"loaded": loaded, "expected": plan["expected_rows"]})
            elif receipt_count == 1 and raw_count == plan["expected_rows"]:
                show("raw_load", {"status": "already_loaded", "rows": raw_count})
            else:
                raise RuntimeError("Existing receipt or RAW rows need investigation")

            cursor.execute(STATE_SQL, (attempt_id,))
            before = cursor.fetchall()
            show("health_before_processing", before)
            if before == [("PENDING_PROCESS", plan["expected_rows"],
                           plan["expected_rows"], 0, None, None)]:
                cursor.execute(
                    "CALL QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT(%s)",
                    (attempt_id,),
                )
                outcome = json.loads(cursor.fetchone()[0])
                show("processing", outcome)
                if outcome.get("status") != "complete" or outcome.get("processed_rows") != plan["expected_rows"]:
                    raise RuntimeError("Processing result needs investigation")
            elif len(before) != 1 or before[0][0] != "RECONCILED":
                raise RuntimeError("Unexpected batch health before processing")

            cursor.execute(STATE_SQL, (attempt_id,))
            after = cursor.fetchall()
            show("health_after_processing", after)
            if (len(after) != 1 or after[0][0] != "RECONCILED"
                    or after[0][1:5] != (plan["expected_rows"],) * 4):
                raise RuntimeError("Batch did not reconcile after processing")

            cursor.execute(Path("sql/phase3_sample_analysis.sql").read_text())
            sample = cursor.fetchall()
            show("current_seattle_sample", sample)
            if len(sample) != 1:
                raise RuntimeError("Expected one Seattle sample aggregate")


if __name__ == "__main__":
    main()
