"""Preview or process one later update in the isolated fixture database."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.build_phase2_fixture_attempts import FIXTURES, SEQUENCE
from scripts.phase2_fixture_original import (
    ATTEMPT_ID as ORIGINAL_ATTEMPT, CURATED, EVENT_ID, EXPECTED_AFTER as ORIGINAL_COUNTS,
    RAW, _counts, _guard_unique_keys,
)
from scripts.phase2_fixture_raw_load import _hash_feature


ATTEMPT_ID = SEQUENCE[1][0]
ORIGINAL_PROCESS_ID = "542ce981de9d45689e822581a89ee0f7"
EXPECTED_AFTER = {
    **ORIGINAL_COUNTS,
    "STG_EVENT_REVISION": 2,
    "FACT_EVENT_REVISION": 2,
    "BRIDGE_EVENT_SITE": 6,
    "FACT_BATCH_RUN": 2,
    "BATCH_PROCESS_ATTEMPT": 2,
}


def _feature(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _current(cursor) -> list[tuple]:
    cursor.execute(f"""
        SELECT CANONICAL_EVENT_ID, SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH
        FROM {CURATED}.EVENT_CURRENT
    """)
    return cursor.fetchall()


def _guard_raw(cursor) -> str:
    source = _feature(SEQUENCE[1][1])
    expected_hash = _hash_feature(source)
    cursor.execute(f"""
        SELECT a.EXTRACT_STATUS, a.LOAD_STATUS, a.SOURCE_ROWS_RETURNED,
               a.RAW_ROWS_WRITTEN, a.LOADED_ROWS,
               COALESCE(ARRAY_SIZE(a.COVERAGE_GAPS), 0),
               a.MANIFEST:fixture_only::BOOLEAN,
               r.PAYLOAD_HASH, r.PAYLOAD:id::VARCHAR,
               r.PAYLOAD:properties:status::VARCHAR
        FROM {RAW}.BATCH_ATTEMPT a
        JOIN {RAW}.RAW_EVENT_RECORDS r ON a.ATTEMPT_ID = r.ATTEMPT_ID
        WHERE a.ATTEMPT_ID = %s
    """, (ATTEMPT_ID,))
    if cursor.fetchall() != [("complete", "complete", 1, 1, 1, 0, True,
                              expected_hash, EVENT_ID, "reviewed")]:
        raise RuntimeError("update fixture RAW receipt or source row differs")
    return expected_hash


def _guard_before(cursor) -> str:
    expected_hash = _guard_raw(cursor)
    if _counts(cursor) != ORIGINAL_COUNTS:
        raise RuntimeError("fixture model is not at the measured original state")
    original_hash = _hash_feature(_feature(SEQUENCE[0][1]))
    if _current(cursor) != [(EVENT_ID, "reviewed", 1.08, original_hash)]:
        raise RuntimeError("current event is not the measured original revision")
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (ORIGINAL_ATTEMPT,))
    if cursor.fetchall() != [(ORIGINAL_PROCESS_ID, "complete", 1)]:
        raise RuntimeError("original processing audit differs")
    _guard_unique_keys(cursor)
    return expected_hash


def _guard_after(cursor, outcome: dict, expected_hash: str) -> dict[str, int]:
    if (outcome.get("attempt_id") != ATTEMPT_ID
            or outcome.get("status") != "complete"
            or outcome.get("loaded_rows") != 1
            or outcome.get("processed_rows") != 1
            or outcome.get("rejected_rows") != 0
            or outcome.get("revision_rows_merged") != 1
            or not outcome.get("process_attempt_id")
            or outcome["process_attempt_id"] == ORIGINAL_PROCESS_ID):
        raise RuntimeError(f"update fixture processing outcome differs: {outcome}")
    counts = _counts(cursor)
    if counts != EXPECTED_AFTER:
        raise RuntimeError(f"update fixture model counts differ: {counts}")
    if _current(cursor) != [(EVENT_ID, "reviewed", 1.28, expected_hash)]:
        raise RuntimeError("current event did not advance to the later update")
    original_hash = _hash_feature(_feature(SEQUENCE[0][1]))
    cursor.execute(f"""
        SELECT SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH
        FROM {CURATED}.FACT_EVENT_REVISION
        WHERE CANONICAL_EVENT_ID = %s ORDER BY SOURCE_UPDATED_AT
    """, (EVENT_ID,))
    if cursor.fetchall() != [("reviewed", 1.08, original_hash),
                             ("reviewed", 1.28, expected_hash)]:
        raise RuntimeError("fixture revision history lacks original and update")
    cursor.execute(f"""
        SELECT STATUS, REVISION_ROWS_MERGED FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s AND PROCESS_ATTEMPT_ID = %s
    """, (ATTEMPT_ID, outcome["process_attempt_id"]))
    if cursor.fetchall() != [("complete", 1)]:
        raise RuntimeError("update processing audit differs")
    _guard_unique_keys(cursor)
    return counts


def preview() -> None:
    print("Phase 2 update fixture: preview only; no Snowflake connection")
    print(f"Attempt: {ATTEMPT_ID}; original process: {ORIGINAL_PROCESS_ID}")
    print("Guard: complete synthetic RAW update and exact measured original state")
    print("Then: one procedure CALL; expect two revisions and current magnitude 1.28")


def execute_update() -> dict:
    """Call once after separate warehouse-cost and conditional-delete approval."""
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            expected_hash = _guard_before(cursor)
            cursor.execute(f"CALL {CURATED}.PROCESS_LOADED_ATTEMPT(%s)", (ATTEMPT_ID,))
            outcome = json.loads(cursor.fetchone()[0])
            return {"outcome": outcome, "counts": _guard_after(cursor, outcome, expected_hash)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run one paid update fixture call")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_update(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
