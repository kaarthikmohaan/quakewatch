"""Read isolated old-origin fixture state without changing Snowflake data."""

from __future__ import annotations

import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.fixture_original import CURATED, _counts
from scripts.evidence.phase2.old_origin_original import EXPECTED_AFTER
from scripts.fixtures.build_phase2_old_origin_attempts import SEQUENCE


def main() -> None:
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            counts = _counts(cursor)
            cursor.execute(
                f"""
                SELECT ATTEMPT_ID, STATUS, REVISION_ROWS_MERGED
                FROM {CURATED}.BATCH_PROCESS_ATTEMPT
                WHERE ATTEMPT_ID IN (%s, %s)
                ORDER BY ATTEMPT_ID
            """,
                tuple(sorted(attempt for attempt, _ in SEQUENCE)),
            )
            audits = cursor.fetchall()
            cursor.execute(f"""
                SELECT CANONICAL_EVENT_ID, MAGNITUDE,
                       TO_CHAR(ORIGIN_TIME, 'YYYY-MM-DD')
                FROM {CURATED}.EVENT_CURRENT
                ORDER BY CANONICAL_EVENT_ID
            """)
            current = cursor.fetchall()
    print(
        json.dumps(
            {
                "counts": counts,
                "differences_from_original": {
                    name: {"expected": EXPECTED_AFTER[name], "actual": value}
                    for name, value in counts.items()
                    if value != EXPECTED_AFTER[name]
                },
                "old_origin_audits": audits,
                "current": current,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
