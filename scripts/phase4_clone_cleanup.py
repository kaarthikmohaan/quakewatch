"""Drop only the completed Phase 4 fixture demo clone after separate approval."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.phase4_clone_recovery import CLONE, SOURCE


def validate_cleanup(source_rows: int, clone_rows: int,
                     source_original: int, clone_changed: int) -> None:
    if (source_rows, clone_rows, source_original, clone_changed) != (5, 5, 1, 1):
        raise RuntimeError("demo clone state differs from recorded result; do not drop")


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
                SELECT TABLE_NAME, TABLE_TYPE, TABLE_OWNER
                FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'CURATED'
                  AND TABLE_NAME = 'QW_PHASE4_REVISION_DEMO'
            """)
            if cursor.fetchall() != [("QW_PHASE4_REVISION_DEMO", "BASE TABLE", "QUAKEWATCH_ROLE")]:
                raise RuntimeError("demo clone is absent or differs; do not drop")
            cursor.execute(f"SELECT COUNT(*) FROM {SOURCE}")
            source_rows = int(cursor.fetchone()[0])
            cursor.execute(f"SELECT COUNT(*) FROM {CLONE}")
            clone_rows = int(cursor.fetchone()[0])
            cursor.execute(f"""
                SELECT COUNT(*) FROM {SOURCE}
                WHERE CANONICAL_EVENT_ID = 'qw-old-origin-001' AND MAGNITUDE = 1.1
            """)
            source_original = int(cursor.fetchone()[0])
            cursor.execute(f"""
                SELECT COUNT(*) FROM {CLONE}
                WHERE CANONICAL_EVENT_ID = 'qw-old-origin-001' AND MAGNITUDE = 1001.1
            """)
            clone_changed = int(cursor.fetchone()[0])
            validate_cleanup(source_rows, clone_rows, source_original, clone_changed)
            cursor.execute(f"DROP TABLE {CLONE}")
            drop_query_id = cursor.sfqid
            cursor.execute("""
                SELECT COUNT(*) FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'CURATED' AND TABLE_NAME = 'QW_PHASE4_REVISION_DEMO'
            """)
            if int(cursor.fetchone()[0]) != 0:
                raise RuntimeError("demo clone still appears in metadata")
            return {"status": "pass", "dropped_clone": CLONE,
                    "source_rows_unchanged": source_rows, "drop_query_id": drop_query_id}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run approved demo-clone DROP")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        print("Phase 4 clone cleanup preview only; no Snowflake connection")
        print(f"Guard source and clone result, then DROP only {CLONE}")


if __name__ == "__main__":
    main()
