"""Shared steps for applying reviewed SQL and deploying the Snowpark procedure."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from scripts.pipeline.build_procedure_bundle import REPO_ROOT

SQL_DIR = REPO_ROOT / "sql"
STAGE = "@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure"
PROCEDURE_SQL = SQL_DIR / "setup/09_create_procedure.sql"


def sql_statements(path: Path) -> list[str]:
    """Split a reviewed SQL file with the connector's splitter, keeping procedure bodies intact."""
    from snowflake.connector.util_text import split_statements

    return [
        statement.strip()
        for statement, _ in split_statements(StringIO(path.read_text()), remove_comments=True)
        if statement.strip()
    ]


def run_sql_file(cursor, path: Path) -> int:
    statements = sql_statements(path)
    for statement in statements:
        cursor.execute(statement)
    return len(statements)


def upload_and_create_procedure(cursor, bundle: Path) -> None:
    """Upload the bundle over the previous one, then replace the procedure."""
    cursor.execute(f"PUT '{bundle.as_uri()}' {STAGE} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
    columns = [column[0].lower() for column in cursor.description]
    upload = dict(zip(columns, cursor.fetchone(), strict=True))
    if upload.get("status") != "UPLOADED":
        raise RuntimeError(f"procedure bundle was not uploaded: {upload}")
    run_sql_file(cursor, PROCEDURE_SQL)
