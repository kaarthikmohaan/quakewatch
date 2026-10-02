"""Read-only state check after the new-batch recovery guard stopped."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.first_failure_demo import ATTEMPT_ID, _raw_hash
from scripts.evidence.phase2.fixture_original import CURATED
from scripts.evidence.phase2.recovery_demo import _duplicates, _snapshot


def execute() -> dict:
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            snapshot = _snapshot(cursor, ATTEMPT_ID)
            raw_hash = _raw_hash(cursor) if snapshot["raw"] == 1 else None
            cursor.execute(f"""
                SELECT STATUS, LOADED_ROWS, PROCESSED_ROWS, REJECTED_ROWS,
                       REVISION_ROWS_MERGED, ERROR_TYPE
                FROM {CURATED}.BATCH_PROCESS_ATTEMPT
                WHERE ATTEMPT_ID = %s ORDER BY STARTED_AT
            """, (ATTEMPT_ID,))
            audits = [dict(zip(("status", "loaded", "processed", "rejected",
                                "merged", "error_type"), row, strict=True))
                      for row in cursor.fetchall()]
            cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.FACT_BATCH_RUN "
                           "WHERE ATTEMPT_ID = %s", (ATTEMPT_ID,))
            batch_facts = int(cursor.fetchone()[0])
            cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.STG_EVENT_REVISION "
                           "WHERE ATTEMPT_ID = %s", (ATTEMPT_ID,))
            staged_rows = int(cursor.fetchone()[0])
            return {"attempt_id": ATTEMPT_ID, "snapshot": snapshot,
                    "raw_hash": raw_hash, "audits": audits,
                    "attempt_batch_facts": batch_facts,
                    "attempt_staged_rows": staged_rows,
                    "duplicate_groups": _duplicates(cursor)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run paid read-only Snowflake queries")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True, default=str))
    else:
        print("First-failure state check: preview only; no Snowflake connection")
        print(f"Attempt: {ATTEMPT_ID}; read-only RAW, audit, model, and duplicate counts")


if __name__ == "__main__":
    main()
