"""Preview or process one tombstone in the isolated fixture database."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.phase2_fixture_original import (
    CURATED,
    EVENT_ID,
    RAW,
    _counts,
    _guard_unique_keys,
)
from scripts.evidence.phase2.phase2_fixture_raw_load import _hash_feature
from scripts.evidence.phase2.phase2_fixture_update import (
    ATTEMPT_ID as UPDATE_ATTEMPT,
)
from scripts.evidence.phase2.phase2_fixture_update import (
    EXPECTED_AFTER as UPDATE_COUNTS,
)
from scripts.fixtures.build_phase2_fixture_attempts import FIXTURES, SEQUENCE

ATTEMPT_ID = SEQUENCE[2][0]
UPDATE_PROCESS_ID = "36ea2d1efb2144b1a4aad3e107f30842"
EXPECTED_AFTER = {
    **UPDATE_COUNTS,
    "STG_EVENT_REVISION": 3,
    "FACT_EVENT_REVISION": 3,
    "BRIDGE_EVENT_SITE": 9,
    "FACT_BATCH_RUN": 3,
    "BATCH_PROCESS_ATTEMPT": 3,
    "DIM_EVENT_STATUS": 2,
}


def _feature(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _guard_raw(cursor) -> str:
    expected_hash = _hash_feature(_feature(SEQUENCE[2][1]))
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
                              expected_hash, EVENT_ID, "deleted")]:
        raise RuntimeError("deletion fixture RAW receipt or source row differs")
    return expected_hash


def _guard_before(cursor) -> str:
    expected_hash = _guard_raw(cursor)
    if _counts(cursor) != UPDATE_COUNTS:
        raise RuntimeError("fixture model is not at the measured update state")
    update_hash = _hash_feature(_feature(SEQUENCE[1][1]))
    cursor.execute(f"""
        SELECT CANONICAL_EVENT_ID, SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH
        FROM {CURATED}.EVENT_CURRENT
    """)
    if cursor.fetchall() != [(EVENT_ID, "reviewed", 1.28, update_hash)]:
        raise RuntimeError("current event is not the measured update revision")
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (UPDATE_ATTEMPT,))
    if cursor.fetchall() != [(UPDATE_PROCESS_ID, "complete", 1)]:
        raise RuntimeError("update processing audit differs")
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
            or outcome["process_attempt_id"] == UPDATE_PROCESS_ID):
        raise RuntimeError(f"deletion fixture processing outcome differs: {outcome}")
    counts = _counts(cursor)
    if counts != EXPECTED_AFTER:
        raise RuntimeError(f"deletion fixture model counts differ: {counts}")
    cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.EVENT_CURRENT")
    if cursor.fetchone()[0] != 0:
        raise RuntimeError("deleted event remains current")
    cursor.execute(f"""
        SELECT SOURCE_STATUS, PAYLOAD_HASH FROM {CURATED}.FACT_EVENT_REVISION
        WHERE CANONICAL_EVENT_ID = %s ORDER BY SOURCE_UPDATED_AT
    """, (EVENT_ID,))
    expected_history = [
        ("reviewed", _hash_feature(_feature(SEQUENCE[0][1]))),
        ("reviewed", _hash_feature(_feature(SEQUENCE[1][1]))),
        ("deleted", expected_hash),
    ]
    if cursor.fetchall() != expected_history:
        raise RuntimeError("fixture revision history lacks preserved tombstone")
    cursor.execute(f"""
        SELECT STATUS, REVISION_ROWS_MERGED FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s AND PROCESS_ATTEMPT_ID = %s
    """, (ATTEMPT_ID, outcome["process_attempt_id"]))
    if cursor.fetchall() != [("complete", 1)]:
        raise RuntimeError("deletion processing audit differs")
    _guard_unique_keys(cursor)
    return counts


def preview() -> None:
    print("Phase 2 deletion fixture: preview only; no Snowflake connection")
    print(f"Attempt: {ATTEMPT_ID}; update process: {UPDATE_PROCESS_ID}")
    print("Guard: complete synthetic deletion RAW and exact measured update state")
    print("Then: one procedure CALL; expect three historical revisions and zero current rows")


def execute_deletion() -> dict:
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
    parser.add_argument("--execute", action="store_true", help="run one paid tombstone fixture call")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_deletion(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
