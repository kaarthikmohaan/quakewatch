"""Guard the later update to an old-origin synthetic event."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.phase2_fixture_original import CURATED, _counts, _guard_unique_keys
from scripts.evidence.phase2.phase2_old_origin_original import (
    ATTEMPT_ID as ORIGINAL_ATTEMPT,
)
from scripts.evidence.phase2.phase2_old_origin_original import (
    EVENT_ID,
    _expected_hash,
    _guard_raw,
)
from scripts.evidence.phase2.phase2_old_origin_original import (
    EXPECTED_AFTER as ORIGINAL_COUNTS,
)
from scripts.fixtures.build_phase2_old_origin_attempts import SEQUENCE

ATTEMPT_ID = SEQUENCE[1][0]
EXPECTED_AFTER = {
    **ORIGINAL_COUNTS,
    "STG_EVENT_REVISION": 6,
    "FACT_EVENT_REVISION": 5,
    "BRIDGE_EVENT_SITE": 15,
    "FACT_BATCH_RUN": 6,
    "BATCH_PROCESS_ATTEMPT": 6,
    "DIM_DATE": 4,
}


def _original_process_id(cursor) -> str:
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (ORIGINAL_ATTEMPT,))
    rows = cursor.fetchall()
    if (len(rows) != 1 or rows[0][1:] != ("complete", 1)
            or not rows[0][0]):
        raise RuntimeError("old-origin original processing audit differs")
    return rows[0][0]


def _guard_before(cursor, original_process_id: str) -> str:
    _guard_raw(cursor)
    if _counts(cursor) != ORIGINAL_COUNTS:
        raise RuntimeError("fixture model is not at measured old-origin original state")
    cursor.execute(f"""
        SELECT CANONICAL_EVENT_ID, MAGNITUDE, PAYLOAD_HASH,
               TO_CHAR(ORIGIN_TIME, 'YYYY-MM-DD')
        FROM {CURATED}.EVENT_CURRENT
    """)
    if cursor.fetchall() != [(EVENT_ID, 1.1, _expected_hash(SEQUENCE[0][1]),
                              "2020-01-15")]:
        raise RuntimeError("old-origin current row differs before update")
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (ORIGINAL_ATTEMPT,))
    if cursor.fetchall() != [(original_process_id, "complete", 1)]:
        raise RuntimeError("old-origin original processing audit differs")
    _guard_unique_keys(cursor)
    return _expected_hash(SEQUENCE[1][1])


def _guard_after(cursor, outcome: dict, expected_hash: str,
                 original_process_id: str) -> dict[str, int]:
    if (outcome.get("attempt_id") != ATTEMPT_ID
            or outcome.get("status") != "complete"
            or outcome.get("loaded_rows") != 1
            or outcome.get("processed_rows") != 1
            or outcome.get("rejected_rows") != 0
            or outcome.get("revision_rows_merged") != 1
            or not outcome.get("process_attempt_id")
            or outcome["process_attempt_id"] == original_process_id):
        raise RuntimeError(f"old-origin update processing outcome differs: {outcome}")
    counts = _counts(cursor)
    if counts != EXPECTED_AFTER:
        raise RuntimeError(f"old-origin update model counts differ: {counts}")
    cursor.execute(f"""
        SELECT CANONICAL_EVENT_ID, SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH,
               TO_CHAR(ORIGIN_TIME, 'YYYY-MM-DD')
        FROM {CURATED}.EVENT_CURRENT
    """)
    if cursor.fetchall() != [(EVENT_ID, "reviewed", 1.3, expected_hash, "2020-01-15")]:
        raise RuntimeError("old-origin current row did not select later update")
    cursor.execute(f"""
        SELECT SOURCE_STATUS, MAGNITUDE, PAYLOAD_HASH,
               TO_CHAR(ORIGIN_TIME, 'YYYY-MM-DD')
        FROM {CURATED}.FACT_EVENT_REVISION
        WHERE CANONICAL_EVENT_ID = %s ORDER BY SOURCE_UPDATED_AT
    """, (EVENT_ID,))
    if cursor.fetchall() != [
        ("reviewed", 1.1, _expected_hash(SEQUENCE[0][1]), "2020-01-15"),
        ("reviewed", 1.3, expected_hash, "2020-01-15"),
    ]:
        raise RuntimeError("old-origin revision history differs")
    cursor.execute(f"""
        SELECT STATUS, REVISION_ROWS_MERGED FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s AND PROCESS_ATTEMPT_ID = %s
    """, (ATTEMPT_ID, outcome["process_attempt_id"]))
    if cursor.fetchall() != [("complete", 1)]:
        raise RuntimeError("old-origin update processing audit differs")
    _guard_unique_keys(cursor)
    return counts


def preview() -> None:
    print("Phase 2 old-origin update: preview only; no Snowflake connection")
    print(f"Attempt: {ATTEMPT_ID}")
    print("Guard: original 2020-origin revision has completed with its process ID")
    print("Then: one procedure CALL; expect two old-origin revisions and current magnitude 1.3")


def execute_update(original_process_id: str | None = None) -> dict:
    """Call once after separate warehouse-cost and conditional-delete approval."""
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            if original_process_id is None:
                original_process_id = _original_process_id(cursor)
            expected_hash = _guard_before(cursor, original_process_id)
            cursor.execute(f"CALL {CURATED}.PROCESS_LOADED_ATTEMPT(%s)", (ATTEMPT_ID,))
            outcome = json.loads(cursor.fetchone()[0])
            return {"outcome": outcome,
                    "counts": _guard_after(cursor, outcome, expected_hash, original_process_id)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run one paid fixture procedure call")
    parser.add_argument("--original-process-id", help="optional ID printed by the original call")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_update(args.original_process_id), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
