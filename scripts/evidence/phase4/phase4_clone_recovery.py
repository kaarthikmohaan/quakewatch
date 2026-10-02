"""Guarded optional clone/Time Travel drill in the isolated fixture database."""

from __future__ import annotations

import argparse
import json
import re

from quakewatch.raw_load import connect_project
from scripts.evidence.phase4.phase4_recovery_preflight import CLONE_NAME, SOURCE, validate


CLONE = f"QUAKEWATCH_PHASE2_FIXTURE.CURATED.{CLONE_NAME}"
QUERY_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


def before_query(query_id: str) -> str:
    if not QUERY_ID.fullmatch(query_id):
        raise ValueError("invalid MERGE query ID")
    return f"SELECT COUNT(*), MIN(MAGNITUDE), MAX(MAGNITUDE) FROM {CLONE} BEFORE (STATEMENT => '{query_id}')"


def _count(cursor, table: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cursor.fetchone()[0])


def _target_value(cursor, table: str, key: tuple) -> float:
    cursor.execute(f"""
        SELECT MAGNITUDE FROM {table}
        WHERE CANONICAL_EVENT_ID = %s
          AND SOURCE_UPDATED_AT = TO_TIMESTAMP_TZ(%s)
          AND PAYLOAD_HASH = %s
    """, key)
    values = cursor.fetchall()
    if len(values) != 1 or values[0][0] is None:
        raise RuntimeError("target revision is missing or ambiguous")
    return float(values[0][0])


def execute() -> dict:
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("unexpected role or warehouse")
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_TYPE, TABLE_OWNER, ROW_COUNT,
                       RETENTION_TIME, IS_TRANSIENT
                FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'CURATED'
                  AND TABLE_NAME IN ('FACT_EVENT_REVISION', 'QW_PHASE4_REVISION_DEMO')
            """)
            metadata = cursor.fetchall()
            count = _count(cursor, SOURCE)
            cursor.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                    FROM {SOURCE}
                    GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                    HAVING COUNT(*) > 1
                )
            """)
            validate(metadata, count, int(cursor.fetchone()[0]))
            cursor.execute(f"""
                SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT::VARCHAR, PAYLOAD_HASH,
                       MAGNITUDE
                FROM {SOURCE} WHERE MAGNITUDE IS NOT NULL
                ORDER BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                LIMIT 1
            """)
            target = cursor.fetchone()
            if target is None:
                raise RuntimeError("no fixture magnitude available")
            key = target[:3]
            original = float(target[3])

            # No OR REPLACE or IF NOT EXISTS: a name collision must fail.
            cursor.execute(f"CREATE TABLE {CLONE} CLONE {SOURCE}")
            clone_query_id = cursor.sfqid
            if _count(cursor, CLONE) != count or _target_value(cursor, CLONE, key) != original:
                raise RuntimeError("clone differs from source; inspect clone before retry")

            bad_magnitude = original + 1000.0
            cursor.execute(f"""
                MERGE INTO {CLONE} AS target
                USING (
                    SELECT %s::VARCHAR AS CANONICAL_EVENT_ID,
                           TO_TIMESTAMP_TZ(%s) AS SOURCE_UPDATED_AT,
                           %s::VARCHAR AS PAYLOAD_HASH,
                           %s::FLOAT AS BAD_MAGNITUDE
                ) AS incoming
                ON target.CANONICAL_EVENT_ID = incoming.CANONICAL_EVENT_ID
                   AND target.SOURCE_UPDATED_AT = incoming.SOURCE_UPDATED_AT
                   AND target.PAYLOAD_HASH = incoming.PAYLOAD_HASH
                WHEN MATCHED THEN UPDATE SET MAGNITUDE = incoming.BAD_MAGNITUDE
            """, (*key, bad_magnitude))
            merge_query_id = cursor.sfqid
            if cursor.rowcount != 1:
                raise RuntimeError("bad MERGE did not affect exactly one clone row")
            source_after = _target_value(cursor, SOURCE, key)
            clone_after = _target_value(cursor, CLONE, key)
            if (source_after != original or clone_after != bad_magnitude
                    or _count(cursor, SOURCE) != count or _count(cursor, CLONE) != count):
                raise RuntimeError("clone isolation check failed; preserve state for inspection")
            cursor.execute(before_query(merge_query_id))
            before_count, before_min, before_max = cursor.fetchone()
            cursor.execute(f"""
                SELECT MAGNITUDE FROM {CLONE} BEFORE (STATEMENT => '{merge_query_id}')
                WHERE CANONICAL_EVENT_ID = %s
                  AND SOURCE_UPDATED_AT = TO_TIMESTAMP_TZ(%s)
                  AND PAYLOAD_HASH = %s
            """, key)
            before_values = cursor.fetchall()
            if (int(before_count) != count or len(before_values) != 1
                    or float(before_values[0][0]) != original):
                raise RuntimeError("Time Travel did not return the pre-MERGE value")
            return {
                "status": "pass", "source": SOURCE, "clone": CLONE,
                "source_rows": count, "clone_rows": count,
                "target_event_id": key[0], "original_magnitude": original,
                "clone_bad_magnitude": clone_after,
                "time_travel_rows": int(before_count),
                "time_travel_min_magnitude": float(before_min),
                "time_travel_max_magnitude": float(before_max),
                "clone_query_id": clone_query_id,
                "merge_query_id": merge_query_id,
                "clone_left_for_separate_cleanup_approval": True,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run paid clone and deliberate clone-only MERGE")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        print("Phase 4 recovery preview only; no Snowflake connection")
        print(f"Guard five-row {SOURCE}; create {CLONE}; MERGE one clone-only magnitude")
        print("Verify source unchanged and Time Travel BEFORE MERGE; leave clone for approved cleanup")


if __name__ == "__main__":
    main()
