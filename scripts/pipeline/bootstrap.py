"""Create the project's Snowflake tables and procedure in the documented order.

Preview by default; nothing connects. With ``--execute`` (uses warehouse
credits) it runs as ``QUAKEWATCH_ROLE`` and applies the table DDL, which only
creates missing objects, then uploads the procedure bundle and replaces the
procedure. Run ``sql/phase0_bootstrap.sql`` once with an admin role first; the
health views are created by ``make quality`` when they are absent.
"""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.pipeline.build_procedure_bundle import DEFAULT_OUTPUT, build_bundle
from scripts.pipeline.procedure_deploy import SQL_DIR, run_sql_file, upload_and_create_procedure

TABLE_FILES = (
    "phase1_raw_tables.sql",
    "phase1_update_watermark.sql",
    "phase2_staging_table.sql",
    "phase2_process_attempt.sql",
    "phase2_dimensions_bridge.sql",
    "phase2_revision_current.sql",
    "phase2_batch_fact.sql",
)


def preview() -> None:
    print("Bootstrap: preview only; no Snowflake connection or changes")
    print("Prerequisite: sql/phase0_bootstrap.sql run once with an admin role")
    for number, name in enumerate(TABLE_FILES, start=1):
        print(f"{number}. sql/{name}")
    print(f"{len(TABLE_FILES) + 1}. Upload {DEFAULT_OUTPUT.name} and run sql/phase2_create_procedure.sql")
    print("Health views: created by `make quality` when absent")


def execute() -> dict:
    digest = build_bundle(DEFAULT_OUTPUT)
    applied = {}
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            for name in TABLE_FILES:
                applied[name] = run_sql_file(cursor, SQL_DIR / name)
            upload_and_create_procedure(cursor, DEFAULT_OUTPUT)
    return {"statements_by_file": applied, "procedure_bundle_sha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create QuakeWatch tables and procedure")
    parser.add_argument("--execute", action="store_true", help="connect and run (uses warehouse credits)")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
