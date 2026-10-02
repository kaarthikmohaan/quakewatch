"""Read-only Phase 4 fixture preflight; requires approved Snowflake compute."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project

SOURCE = "QUAKEWATCH_PHASE2_FIXTURE.CURATED.FACT_EVENT_REVISION"
CLONE_NAME = "QW_PHASE4_REVISION_DEMO"


def validate(metadata: list[tuple], exact_count: int, duplicate_groups: int) -> dict:
    """Stop if the sandbox differs from the reviewed five-row fixture."""
    by_name = {row[0]: row for row in metadata}
    source = by_name.get("FACT_EVENT_REVISION")
    if (
        len(metadata) != 1
        or source is None
        or source[1] != "BASE TABLE"
        or source[2] != "QUAKEWATCH_ROLE"
        or source[4] is None
        or int(source[4]) < 1
        or exact_count != 5
        or duplicate_groups != 0
    ):
        raise RuntimeError("fixture preflight differs from reviewed state; stop before clone")
    return {
        "status": "pass",
        "source_table": SOURCE,
        "source_rows": exact_count,
        "source_metadata_rows": int(source[3]),
        "retention_days": int(source[4]),
        "source_is_transient": source[5],
        "clone_name": f"QUAKEWATCH_PHASE2_FIXTURE.CURATED.{CLONE_NAME}",
        "clone_exists": False,
        "duplicate_groups": duplicate_groups,
    }


def execute() -> dict:
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_TIMESTAMP()")
            role, warehouse, checked_at = cursor.fetchone()
            if role != "QUAKEWATCH_ROLE" or warehouse != "QUAKEWATCH_WH":
                raise RuntimeError("unexpected Snowflake role or warehouse")
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_TYPE, TABLE_OWNER, ROW_COUNT,
                       RETENTION_TIME, IS_TRANSIENT
                FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'CURATED'
                  AND TABLE_NAME IN ('FACT_EVENT_REVISION', 'QW_PHASE4_REVISION_DEMO')
                ORDER BY TABLE_NAME
            """)
            metadata = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) FROM {SOURCE}")
            exact_count = int(cursor.fetchone()[0])
            cursor.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                    FROM {SOURCE}
                    GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                    HAVING COUNT(*) > 1
                )
            """)
            duplicate_groups = int(cursor.fetchone()[0])
            result = validate(metadata, exact_count, duplicate_groups)
            result["checked_at"] = str(checked_at)
            result["query_id"] = cursor.sfqid
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run approved Snowflake SELECTs")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        print("Phase 4 fixture preflight preview only; no Snowflake connection")
        print(f"Read-only source: {SOURCE}; absent clone required: {CLONE_NAME}")
        print(
            "Expected: role QUAKEWATCH_ROLE, warehouse QUAKEWATCH_WH, "
            "five source rows, retention >=1 day, zero duplicate groups"
        )


if __name__ == "__main__":
    main()
