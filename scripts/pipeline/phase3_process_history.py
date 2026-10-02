"""Process a bounded number of loaded history attempts with per-attempt checks."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project


PENDING_SQL = """
SELECT ATTEMPT_ID, LOADED_ROWS
FROM QUAKEWATCH.CURATED.V_BATCH_HEALTH
WHERE HEALTH_STATUS = 'PENDING_PROCESS'
  AND BATCH_KIND = 'origin'
  AND EXTRACT_STATUS = 'complete'
  AND LOAD_STATUS = 'complete'
  AND RECEIPT_GAP_COUNT = 0
ORDER BY REQUESTED_STARTTIME, SITE_KEY, ATTEMPT_ID
LIMIT %s
"""
STATE_SQL = """
SELECT HEALTH_STATUS, LOADED_ROWS, RAW_ROWS, STAGING_ROWS,
       PROCESSED_ROWS, REJECTED_ROWS
FROM QUAKEWATCH.CURATED.V_BATCH_HEALTH
WHERE ATTEMPT_ID = %s
"""


def process_history(max_attempts: int) -> dict:
    if not 1 <= max_attempts <= 200:
        raise ValueError("max_attempts must be between 1 and 200")
    completed = []
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 600")
            cursor.execute(PENDING_SQL, (max_attempts,))
            pending = [(attempt_id, int(rows)) for attempt_id, rows in cursor.fetchall()]
            for attempt_id, loaded_rows in pending:
                cursor.execute(STATE_SQL, (attempt_id,))
                before = cursor.fetchall()
                if before != [("PENDING_PROCESS", loaded_rows, loaded_rows, 0, None, None)]:
                    raise RuntimeError(f"pending state changed for {attempt_id}; stop")
                cursor.execute("CALL QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT(%s)",
                               (attempt_id,))
                outcome = json.loads(cursor.fetchone()[0])
                if (outcome.get("attempt_id") != attempt_id
                        or outcome.get("status") != "complete"
                        or outcome.get("loaded_rows") != loaded_rows
                        or outcome.get("processed_rows") != loaded_rows
                        or not outcome.get("process_attempt_id")):
                    raise RuntimeError(f"procedure outcome differs for {attempt_id}; inspect")
                cursor.execute(STATE_SQL, (attempt_id,))
                after = cursor.fetchall()
                if (len(after) != 1 or after[0][0] != "RECONCILED"
                        or after[0][1:5] != (loaded_rows,) * 4
                        or after[0][5] != outcome.get("rejected_rows")):
                    raise RuntimeError(f"post-process health differs for {attempt_id}; inspect")
                completed.append({"attempt_id": attempt_id,
                                  "loaded_rows": loaded_rows,
                                  "rejected_rows": outcome["rejected_rows"],
                                  "process_attempt_id": outcome["process_attempt_id"]})
                print(json.dumps({"completed": len(completed), "selected": len(pending),
                                  "attempt_id": attempt_id, "loaded_rows": loaded_rows,
                                  "rejected_rows": outcome["rejected_rows"]}), flush=True)
    return {"status": "pass", "completed_attempts": len(completed),
            "processed_rows": sum(item["loaded_rows"] for item in completed),
            "rejected_rows": sum(item["rejected_rows"] for item in completed)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_attempts <= 200:
        parser.error("--max-attempts must be between 1 and 200")
    if args.execute:
        print(json.dumps(process_history(args.max_attempts), sort_keys=True), flush=True)
    else:
        print(f"Preview only: select up to {args.max_attempts} pending origin attempts; "
              "no Snowflake connection")
        print("Each live procedure call may use warehouse compute and may remove "
              "curated collision rows while reconciling aliases")


if __name__ == "__main__":
    main()
