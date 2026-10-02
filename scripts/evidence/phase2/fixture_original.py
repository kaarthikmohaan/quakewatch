"""Preview or process the first isolated, synthetic event fixture once."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.fixture_raw_load import _hash_feature
from scripts.fixtures.build_phase2_fixture_attempts import FIXTURES, SEQUENCE
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE

ATTEMPT_ID = SEQUENCE[0][0]
EVENT_ID = "uw714110682"
CURATED = f"{TEST_DATABASE}.CURATED"
RAW = f"{TEST_DATABASE}.RAW"
MODEL_TABLES = (
    "STG_EVENT_REVISION", "FACT_EVENT_REVISION", "BRIDGE_EVENT_SITE",
    "FACT_BATCH_RUN", "BATCH_PROCESS_ATTEMPT", "DIM_SITE", "DIM_DATE",
    "DIM_MAGNITUDE_TYPE", "DIM_EVENT_STATUS",
)
EXPECTED_AFTER = {
    "STG_EVENT_REVISION": 1,
    "FACT_EVENT_REVISION": 1,
    "BRIDGE_EVENT_SITE": 3,
    "FACT_BATCH_RUN": 1,
    "BATCH_PROCESS_ATTEMPT": 1,
    "DIM_SITE": 3,
    "DIM_DATE": 1,
    "DIM_MAGNITUDE_TYPE": 1,
    "DIM_EVENT_STATUS": 1,
}


def _count(cursor, sql: str, params: tuple = ()) -> int:
    cursor.execute(sql, params) if params else cursor.execute(sql)
    return int(cursor.fetchone()[0])


def _counts(cursor) -> dict[str, int]:
    return {name: _count(cursor, f"SELECT COUNT(*) FROM {CURATED}.{name}")
            for name in MODEL_TABLES}


def _guard_raw(cursor) -> str:
    feature = json.loads((FIXTURES / SEQUENCE[0][1]).read_text(encoding="utf-8"))
    expected_hash = _hash_feature(feature)
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
        raise RuntimeError("original fixture RAW receipt or source row differs")
    return expected_hash


def _guard_unique_keys(cursor) -> None:
    for table, columns in (
        ("FACT_EVENT_REVISION", "CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH"),
        ("BRIDGE_EVENT_SITE", "CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY"),
    ):
        duplicates = _count(cursor, f"""
            SELECT COUNT(*) FROM (
                SELECT {columns} FROM {CURATED}.{table}
                GROUP BY {columns} HAVING COUNT(*) > 1
            )
        """)
        if duplicates:
            raise RuntimeError(f"duplicate fixture {table} grain keys")


def _guard_before(cursor) -> str:
    expected_hash = _guard_raw(cursor)
    counts = _counts(cursor)
    if any(counts.values()) or _count(cursor, f"SELECT COUNT(*) FROM {CURATED}.EVENT_CURRENT"):
        raise RuntimeError(f"fixture curated tables must be empty before first call: {counts}")
    return expected_hash


def _guard_after(cursor, outcome: dict, expected_hash: str) -> dict[str, int]:
    if (outcome.get("attempt_id") != ATTEMPT_ID
            or outcome.get("status") != "complete"
            or outcome.get("loaded_rows") != 1
            or outcome.get("processed_rows") != 1
            or outcome.get("rejected_rows") != 0
            or outcome.get("revision_rows_merged") != 1
            or not outcome.get("process_attempt_id")):
        raise RuntimeError(f"original fixture processing outcome differs: {outcome}")
    counts = _counts(cursor)
    if counts != EXPECTED_AFTER:
        raise RuntimeError(f"original fixture model counts differ: {counts}")
    cursor.execute(f"""
        SELECT CANONICAL_EVENT_ID, SOURCE_EVENT_ID, SOURCE_STATUS, MAGNITUDE,
               PAYLOAD_HASH FROM {CURATED}.EVENT_CURRENT
    """)
    if cursor.fetchall() != [(EVENT_ID, EVENT_ID, "reviewed", 1.08, expected_hash)]:
        raise RuntimeError("original fixture current event differs")
    cursor.execute(f"""
        SELECT STATUS, LOADED_ROWS, PROCESSED_ROWS, REJECTED_ROWS,
               REVISION_ROWS_MERGED FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s AND PROCESS_ATTEMPT_ID = %s
    """, (ATTEMPT_ID, outcome["process_attempt_id"]))
    if cursor.fetchall() != [("complete", 1, 1, 0, 1)]:
        raise RuntimeError("original fixture processing audit differs")
    _guard_unique_keys(cursor)
    return counts


def preview() -> None:
    print("Phase 2 original fixture: preview only; no Snowflake connection")
    print(f"Attempt: {ATTEMPT_ID}; target: {CURATED}")
    print("Guard: one complete synthetic RAW row and empty curated model")
    print("Then: one procedure CALL; expect one active magnitude-1.08 revision")


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
