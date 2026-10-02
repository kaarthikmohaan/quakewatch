"""Verify completed old-origin fixture history without calling the procedure."""

from __future__ import annotations

import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.fixture_original import CURATED
from scripts.evidence.phase2.old_origin_original import _guard_raw
from scripts.evidence.phase2.old_origin_update import _expected_hash, _guard_after
from scripts.fixtures.build_phase2_old_origin_attempts import SEQUENCE


def verify(cursor) -> dict:
    _guard_raw(cursor)
    cursor.execute(f"""
        SELECT ATTEMPT_ID, PROCESS_ATTEMPT_ID, STATUS, LOADED_ROWS,
               PROCESSED_ROWS, REJECTED_ROWS, REVISION_ROWS_MERGED
        FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID IN (%s, %s) ORDER BY ATTEMPT_ID
    """, tuple(sorted(attempt for attempt, _ in SEQUENCE)))
    rows = cursor.fetchall()
    by_attempt = {row[0]: row[1:] for row in rows}
    if (len(rows) != 2 or len(by_attempt) != 2
            or set(by_attempt) != {attempt for attempt, _ in SEQUENCE}):
        raise RuntimeError("expected exactly two old-origin process audits")
    original = by_attempt[SEQUENCE[0][0]]
    update = by_attempt[SEQUENCE[1][0]]
    if (original[1:] != ("complete", 1, 1, 0, 1)
            or update[1:] != ("complete", 1, 1, 0, 1)
            or not original[0] or not update[0] or original[0] == update[0]):
        raise RuntimeError("old-origin process audits differ")
    outcome = {
        "attempt_id": SEQUENCE[1][0],
        "process_attempt_id": update[0],
        "status": update[1],
        "loaded_rows": update[2],
        "processed_rows": update[3],
        "rejected_rows": update[4],
        "revision_rows_merged": update[5],
    }
    counts = _guard_after(cursor, outcome, _expected_hash(SEQUENCE[1][1]), original[0])
    return {"status": "verified", "old_origin_revisions": 2,
            "current_magnitude": 1.3, "counts": counts,
            "original_process_attempt_id": original[0],
            "update_process_attempt_id": update[0]}


def main() -> None:
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            print(json.dumps(verify(cursor), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
