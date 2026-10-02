"""Preview or run one guarded Snowflake processing rerun for idempotency."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.pilot import ATTEMPT_ID, _count, _guard_receipt

FIRST_PROCESS_ID = "42fc37d34e1545498ad004d8eeb35b72"
BASE_COUNTS = {
    "STG_EVENT_REVISION": 15,
    "FACT_EVENT_REVISION": 15,
    "BRIDGE_EVENT_SITE": 45,
    "FACT_BATCH_RUN": 1,
    "BATCH_PROCESS_ATTEMPT": 1,
    "DIM_SITE": 3,
}


def preview() -> None:
    print("Phase 2 rerun: preview only; no Snowflake connection or changes")
    print(f"Attempt: {ATTEMPT_ID}; expected current process: {FIRST_PROCESS_ID}")
    print("Guard: complete 15-row RAW receipt and exact first-pilot curated counts")
    print("Then: one procedure CALL; require zero revision merges and unchanged model counts")
    print("Expected processing log count: 1 before, 2 after")


def _model_counts(cursor) -> dict[str, int]:
    return {
        name: _count(cursor, f"SELECT COUNT(*) FROM QUAKEWATCH.CURATED.{name}")
        for name in BASE_COUNTS
    }


def _guard_unique_keys(cursor) -> None:
    for table, columns in (
        ("FACT_EVENT_REVISION", "CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH"),
        ("BRIDGE_EVENT_SITE", "CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY"),
    ):
        duplicates = _count(cursor, f"""
            SELECT COUNT(*) FROM (
                SELECT {columns}
                FROM QUAKEWATCH.CURATED.{table}
                GROUP BY {columns}
                HAVING COUNT(*) > 1
            )
        """)
        if duplicates:
            raise RuntimeError(f"{table} contains duplicate grain keys")


def _guard_before(cursor) -> None:
    _guard_receipt(cursor)
    counts = _model_counts(cursor)
    if counts != BASE_COUNTS:
        raise RuntimeError(f"curated counts differ from first pilot: {counts}")
    cursor.execute("""
        SELECT PROCESS_ATTEMPT_ID, STATUS, LOADED_ROWS, PROCESSED_ROWS,
               REJECTED_ROWS, REVISION_ROWS_MERGED
        FROM QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s
    """, (ATTEMPT_ID,))
    rows = cursor.fetchall()
    if rows != [(FIRST_PROCESS_ID, "complete", 15, 15, 0, 15)]:
        raise RuntimeError("first processing audit differs from the measured pilot")
    cursor.execute("""
        SELECT PROCESS_STATUS, LAST_PROCESS_ATTEMPT_ID
        FROM QUAKEWATCH.CURATED.FACT_BATCH_RUN
        WHERE ATTEMPT_ID = %s
    """, (ATTEMPT_ID,))
    if cursor.fetchall() != [("complete", FIRST_PROCESS_ID)]:
        raise RuntimeError("batch fact does not point to the first completed process")
    _guard_unique_keys(cursor)


def _guard_after(cursor, outcome: dict) -> dict[str, int]:
    if (outcome.get("attempt_id") != ATTEMPT_ID
            or outcome.get("status") != "complete"
            or outcome.get("loaded_rows") != 15
            or outcome.get("processed_rows") != 15
            or outcome.get("rejected_rows") != 0
            or outcome.get("revision_rows_merged") != 0):
        raise RuntimeError(f"rerun did not converge to the same revisions: {outcome}")
    process_id = outcome.get("process_attempt_id")
    if not process_id or process_id == FIRST_PROCESS_ID:
        raise RuntimeError("rerun needs a new processing attempt ID")
    counts = _model_counts(cursor)
    expected = {**BASE_COUNTS, "BATCH_PROCESS_ATTEMPT": 2}
    if counts != expected:
        raise RuntimeError(f"rerun changed model counts unexpectedly: {counts}")
    cursor.execute("""
        SELECT STATUS, LOADED_ROWS, PROCESSED_ROWS, REJECTED_ROWS,
               REVISION_ROWS_MERGED
        FROM QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT
        WHERE PROCESS_ATTEMPT_ID = %s AND ATTEMPT_ID = %s
    """, (process_id, ATTEMPT_ID))
    if cursor.fetchall() != [("complete", 15, 15, 0, 0)]:
        raise RuntimeError("rerun processing audit is incomplete or duplicated")
    cursor.execute("""
        SELECT PROCESS_STATUS, LAST_PROCESS_ATTEMPT_ID
        FROM QUAKEWATCH.CURATED.FACT_BATCH_RUN
        WHERE ATTEMPT_ID = %s
    """, (ATTEMPT_ID,))
    if cursor.fetchall() != [("complete", process_id)]:
        raise RuntimeError("batch fact does not point to the rerun process")
    _guard_unique_keys(cursor)
    return counts


def execute_rerun() -> dict:
    """Make one procedure call after explicit approval for this paid rerun."""
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            _guard_before(cursor)
            cursor.execute(
                "CALL QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT(%s)", (ATTEMPT_ID,)
            )
            outcome = json.loads(cursor.fetchone()[0])
            return {"outcome": outcome, "counts": _guard_after(cursor, outcome)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run one paid Snowflake rerun")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_rerun(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
