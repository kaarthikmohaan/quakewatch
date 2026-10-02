"""Run the reviewed analysis queries read-only and print their results.

Preview by default; nothing connects. With ``--execute`` (uses a little
warehouse time) it runs the site-by-year aggregates and the Seattle-day sample
as ``QUAKEWATCH_ROLE``. Results are printed only; no file is written.
"""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.pipeline.procedure_deploy import SQL_DIR, sql_statements

QUERIES = ("analysis/site_year_aggregates.sql", "analysis/sample_seattle_day.sql")


def run(cursor, relative: str) -> list[dict]:
    rows = []
    for statement in sql_statements(SQL_DIR / relative):
        cursor.execute(statement)
        if cursor.description:
            columns = [column[0].lower() for column in cursor.description]
            rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reviewed analysis queries read-only")
    parser.add_argument(
        "--execute", action="store_true", help="connect and run (uses warehouse credits)"
    )
    args = parser.parse_args()
    if not args.execute:
        print("Analysis queries: preview only; no Snowflake connection")
        for relative in QUERIES:
            print(f"Would run sql/{relative} and print its rows")
        return
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            result = {relative: run(cursor, relative) for relative in QUERIES}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
