"""Preview or process one stale replay in the isolated fixture database."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.phase2_fixture_deletion import (
    ATTEMPT_ID as DELETION_ATTEMPT,
)
from scripts.evidence.phase2.phase2_fixture_deletion import (
    EXPECTED_AFTER as DELETION_COUNTS,
)
from scripts.evidence.phase2.phase2_fixture_deletion import (
    _feature,
)
from scripts.evidence.phase2.phase2_fixture_original import (
    CURATED,
    EVENT_ID,
    RAW,
    _counts,
    _guard_unique_keys,
)
from scripts.evidence.phase2.phase2_fixture_raw_load import _hash_feature
from scripts.fixtures.build_phase2_fixture_attempts import SEQUENCE

ATTEMPT_ID = SEQUENCE[3][0]
DELETION_PROCESS_ID = "5ad657ffe63449d3a3c2b1d37b32ad85"
EXPECTED_AFTER = {
    **DELETION_COUNTS,
    "STG_EVENT_REVISION": 4,
    "FACT_BATCH_RUN": 4,
    "BATCH_PROCESS_ATTEMPT": 4,
}


def _history(cursor) -> list[tuple[str, str]]:
    cursor.execute(f"""
        SELECT SOURCE_STATUS, PAYLOAD_HASH FROM {CURATED}.FACT_EVENT_REVISION
        WHERE CANONICAL_EVENT_ID = %s ORDER BY SOURCE_UPDATED_AT
    """, (EVENT_ID,))
    return cursor.fetchall()


def _expected_history() -> list[tuple[str, str]]:
    return [
        ("reviewed", _hash_feature(_feature(SEQUENCE[0][1]))),
        ("reviewed", _hash_feature(_feature(SEQUENCE[1][1]))),
        ("deleted", _hash_feature(_feature(SEQUENCE[2][1]))),
    ]


def _guard_before(cursor) -> str:
    expected_hash = _expected_history()[0][1]
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
        raise RuntimeError("stale replay RAW receipt or source row differs")
    if _counts(cursor) != DELETION_COUNTS:
        raise RuntimeError("fixture model is not at the measured deletion state")
    cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.EVENT_CURRENT")
    if cursor.fetchone()[0] != 0 or _history(cursor) != _expected_history():
        raise RuntimeError("fixture tombstone/current state differs")
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (DELETION_ATTEMPT,))
    if cursor.fetchall() != [(DELETION_PROCESS_ID, "complete", 1)]:
        raise RuntimeError("deletion processing audit differs")
    _guard_unique_keys(cursor)
    return expected_hash


def _guard_after(cursor, outcome: dict, expected_hash: str) -> dict[str, int]:
    if (outcome.get("attempt_id") != ATTEMPT_ID
            or outcome.get("status") != "complete"
            or outcome.get("loaded_rows") != 1
            or outcome.get("processed_rows") != 1
            or outcome.get("rejected_rows") != 0
            or outcome.get("revision_rows_merged") not in (0, 1)
            or not outcome.get("process_attempt_id")
            or outcome["process_attempt_id"] == DELETION_PROCESS_ID):
        raise RuntimeError(f"stale replay processing outcome differs: {outcome}")
    counts = _counts(cursor)
    if counts != EXPECTED_AFTER:
        raise RuntimeError(f"stale replay model counts differ: {counts}")
    cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.EVENT_CURRENT")
    if cursor.fetchone()[0] != 0:
        raise RuntimeError("stale replay resurrected deleted event")
    if _history(cursor) != _expected_history() or expected_hash != _expected_history()[0][1]:
        raise RuntimeError("stale replay changed logical revision history")
    cursor.execute(f"""
        SELECT STATUS, REVISION_ROWS_MERGED FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s AND PROCESS_ATTEMPT_ID = %s
    """, (ATTEMPT_ID, outcome["process_attempt_id"]))
    if cursor.fetchall() != [("complete", outcome["revision_rows_merged"])]:
        raise RuntimeError("stale replay processing audit differs")
    _guard_unique_keys(cursor)
    return counts


def preview() -> None:
    print("Phase 2 stale replay: preview only; no Snowflake connection")
    print(f"Attempt: {ATTEMPT_ID}; deletion process: {DELETION_PROCESS_ID}")
    print("Guard: complete synthetic old RAW row and exact measured tombstone state")
    print("Then: one procedure CALL; expect three revisions and zero current rows")


def execute_stale_replay() -> dict:
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
    parser.add_argument("--execute", action="store_true", help="run one paid stale replay call")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_stale_replay(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
