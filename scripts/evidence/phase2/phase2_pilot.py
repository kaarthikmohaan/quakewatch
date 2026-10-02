"""Preview or run the first, bounded QuakeWatch Phase 2 Snowflake pilot."""

from __future__ import annotations

import argparse
import json
from io import StringIO
from pathlib import Path

from snowflake.connector.util_text import split_statements

from quakewatch.raw_load import connect_project

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "data" / "procedure" / "quakewatch_procedure.zip"
ATTEMPT_ID = "20260929T075452Z-26375840ea"
EXPECTED_RAW_ROWS = 15
STAGE = "@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure"
DDL_FILES = (
    "phase2_staging_table.sql",
    "phase2_process_attempt.sql",
    "phase2_dimensions_bridge.sql",
    "phase2_revision_current.sql",
    "phase2_batch_fact.sql",
    "phase2_create_procedure.sql",
)


def ddl_statements() -> list[str]:
    """Use the connector's SQL splitter so the procedure body stays intact."""
    statements = []
    for name in DDL_FILES:
        sql = (ROOT / "sql" / name).read_text()
        statements.extend(statement.strip() for statement, _ in
                          split_statements(StringIO(sql), remove_comments=True)
                          if statement.strip())
    return statements


def preview() -> None:
    print("Phase 2 pilot: preview only; no Snowflake connection or changes")
    print(f"Attempt: {ATTEMPT_ID} ({EXPECTED_RAW_ROWS} expected RAW rows)")
    print(f"Bundle: {BUNDLE}")
    print(f"Upload destination: {STAGE}/quakewatch_procedure.zip")
    print("DDL order: " + ", ".join(DDL_FILES))
    print("Guard: curated schema must be empty; receipt and RAW count must match")
    print("Then: one CALL, count checks, and stop")


def _count(cursor, sql: str, params: tuple = ()) -> int:
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    return cursor.fetchone()[0]


def _guard_empty_curated(cursor) -> None:
    for kind in ("TABLES", "VIEWS", "PROCEDURES"):
        command = "SHOW USER PROCEDURES" if kind == "PROCEDURES" else f"SHOW {kind}"
        cursor.execute(f"{command} IN SCHEMA QUAKEWATCH.CURATED")
        rows = cursor.fetchall()
        if rows:
            columns = [column[0].lower() for column in cursor.description]
            name_index = columns.index("name") if "name" in columns else None
            names = [str(row[name_index]) for row in rows] if name_index is not None else [
                f"{len(rows)} object(s)"
            ]
            raise RuntimeError(
                f"CURATED already has {kind.lower()}: {', '.join(names)}; stop for schema review"
            )


def _guard_receipt(cursor) -> None:
    cursor.execute("""
        SELECT EXTRACT_STATUS, LOAD_STATUS, SOURCE_ROWS_RETURNED,
               RAW_ROWS_WRITTEN, LOADED_ROWS,
               COALESCE(ARRAY_SIZE(COVERAGE_GAPS), 0)
        FROM QUAKEWATCH.RAW.BATCH_ATTEMPT WHERE ATTEMPT_ID = %s
    """, (ATTEMPT_ID,))
    rows = cursor.fetchall()
    if rows != [("complete", "complete", 15, 15, 15, 0)]:
        raise RuntimeError("pilot receipt is absent, duplicated, incomplete, or mismatched")
    raw = _count(cursor,
                 "SELECT COUNT(*) FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS WHERE ATTEMPT_ID = %s",
                 (ATTEMPT_ID,))
    if raw != EXPECTED_RAW_ROWS:
        raise RuntimeError("pilot RAW row count differs from the complete receipt")


def execute_pilot() -> dict:
    """Run once after explicit owner approval for cost and curated DML."""
    if not BUNDLE.is_file():
        raise FileNotFoundError("build the local procedure ZIP first")
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            _guard_empty_curated(cursor)
            _guard_receipt(cursor)
            cursor.execute(
                f"PUT '{BUNDLE.as_uri()}' {STAGE} AUTO_COMPRESS=FALSE OVERWRITE=FALSE"
            )
            columns = [column[0].lower() for column in cursor.description]
            upload = dict(zip(columns, cursor.fetchone(), strict=True))
            if upload.get("status") != "UPLOADED":
                raise RuntimeError("procedure ZIP was not newly uploaded; stop for stage review")
            for statement in ddl_statements():
                cursor.execute(statement)
            cursor.execute(
                "CALL QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT(%s)", (ATTEMPT_ID,)
            )
            outcome = json.loads(cursor.fetchone()[0])
            if outcome.get("status") != "complete" or outcome.get("loaded_rows") != 15:
                raise RuntimeError("pilot procedure did not return a complete 15-row outcome")
            counts = {}
            for name in (
                "STG_EVENT_REVISION", "FACT_EVENT_REVISION", "BRIDGE_EVENT_SITE",
                "FACT_BATCH_RUN", "BATCH_PROCESS_ATTEMPT", "DIM_SITE",
            ):
                counts[name] = _count(cursor, f"SELECT COUNT(*) FROM QUAKEWATCH.CURATED.{name}")
            if (counts["STG_EVENT_REVISION"] != 15
                    or not 0 <= counts["FACT_EVENT_REVISION"] <= 15
                    or counts["BRIDGE_EVENT_SITE"] != 3 * counts["FACT_EVENT_REVISION"]
                    or counts["FACT_BATCH_RUN"] != 1
                    or counts["BATCH_PROCESS_ATTEMPT"] != 1
                    or counts["DIM_SITE"] != 3):
                raise RuntimeError(f"pilot model counts require investigation: {counts}")
            return {"outcome": outcome, "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="connect and run the bounded pilot")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_pilot(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
