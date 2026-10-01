"""Preview or process the first old-origin event in isolated fixture CURATED."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.build_phase2_fixture_attempts import FIXTURES
from scripts.build_phase2_old_origin_attempts import SEQUENCE
from scripts.phase2_fixture_original import CURATED, RAW, _counts, _guard_unique_keys
from scripts.phase2_fixture_raw_load import _hash_feature
from scripts.phase2_fixture_stale_replay import (
    ATTEMPT_ID as REPLAY_ATTEMPT, EXPECTED_AFTER as REPLAY_COUNTS,
)


ATTEMPT_ID = SEQUENCE[0][0]
UPDATE_ATTEMPT_ID = SEQUENCE[1][0]
EVENT_ID = "qw-old-origin-001"
REPLAY_PROCESS_ID = "516de8b981d7486d85b27ccf1d974fb0"
EXPECTED_AFTER = {
    **REPLAY_COUNTS,
    "STG_EVENT_REVISION": 5,
    "FACT_EVENT_REVISION": 4,
    "BRIDGE_EVENT_SITE": 12,
    "FACT_BATCH_RUN": 5,
    "BATCH_PROCESS_ATTEMPT": 5,
    "DIM_DATE": 2,
}


def _expected_hash(name: str) -> str:
    return _hash_feature(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _guard_raw(cursor) -> str:
    expected = []
    for attempt_id, fixture_name in SEQUENCE:
        expected.append((attempt_id, "complete", "complete", 1, 1, 1, 0, True,
                         _expected_hash(fixture_name), EVENT_ID, "reviewed"))
    cursor.execute(f"""
        SELECT a.ATTEMPT_ID, a.EXTRACT_STATUS, a.LOAD_STATUS,
               a.SOURCE_ROWS_RETURNED, a.RAW_ROWS_WRITTEN, a.LOADED_ROWS,
               COALESCE(ARRAY_SIZE(a.COVERAGE_GAPS), 0),
               a.MANIFEST:fixture_only::BOOLEAN,
               r.PAYLOAD_HASH, r.PAYLOAD:id::VARCHAR,
               r.PAYLOAD:properties:status::VARCHAR
        FROM {RAW}.BATCH_ATTEMPT a
        JOIN {RAW}.RAW_EVENT_RECORDS r ON a.ATTEMPT_ID = r.ATTEMPT_ID
        WHERE a.ATTEMPT_ID IN (%s, %s) ORDER BY a.ATTEMPT_ID
    """, tuple(sorted((ATTEMPT_ID, UPDATE_ATTEMPT_ID))))
    if cursor.fetchall() != sorted(expected):
        raise RuntimeError("old-origin fixture RAW receipts or source rows differ")
    return _expected_hash(SEQUENCE[0][1])


def _guard_before(cursor) -> str:
    expected_hash = _guard_raw(cursor)
    if _counts(cursor) != REPLAY_COUNTS:
        raise RuntimeError("fixture curated model is not at measured stale-replay state")
    cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.EVENT_CURRENT")
    if cursor.fetchone()[0] != 0:
        raise RuntimeError("fixture current view changed before old-origin call")
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (REPLAY_ATTEMPT,))
    if cursor.fetchall() != [(REPLAY_PROCESS_ID, "complete", 1)]:
        raise RuntimeError("stale-replay processing audit differs")
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
            or outcome["process_attempt_id"] == REPLAY_PROCESS_ID):
        raise RuntimeError(f"old-origin original processing outcome differs: {outcome}")
    counts = _counts(cursor)
    if counts != EXPECTED_AFTER:
        raise RuntimeError(f"old-origin original model counts differ: {counts}")
    cursor.execute(f"""
        SELECT CANONICAL_EVENT_ID, SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH,
               TO_CHAR(ORIGIN_TIME, 'YYYY-MM-DD')
        FROM {CURATED}.EVENT_CURRENT
    """)
    if cursor.fetchall() != [(EVENT_ID, "reviewed", 1.1, expected_hash, "2020-01-15")]:
        raise RuntimeError("old-origin original is not the current event")
    cursor.execute(f"""
        SELECT SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH,
               TO_CHAR(ORIGIN_TIME, 'YYYY-MM-DD')
        FROM {CURATED}.FACT_EVENT_REVISION WHERE CANONICAL_EVENT_ID = %s
    """, (EVENT_ID,))
    if cursor.fetchall() != [("reviewed", 1.1, expected_hash, "2020-01-15")]:
        raise RuntimeError("old-origin original revision fact differs")
    cursor.execute(f"""
        SELECT STATUS, REVISION_ROWS_MERGED FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s AND PROCESS_ATTEMPT_ID = %s
    """, (ATTEMPT_ID, outcome["process_attempt_id"]))
    if cursor.fetchall() != [("complete", 1)]:
        raise RuntimeError("old-origin original processing audit differs")
    _guard_unique_keys(cursor)
    return counts


def preview() -> None:
    print("Phase 2 old-origin original: preview only; no Snowflake connection")
    print(f"Attempt: {ATTEMPT_ID}; later update loaded but not processed")
    print("Guard: two complete synthetic RAW receipts and measured stale-replay curated state")
    print("Then: one procedure CALL; expect one 2020-origin current revision at magnitude 1.1")


def execute_original() -> dict:
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
    parser.add_argument("--execute", action="store_true", help="run one paid fixture procedure call")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_original(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
