"""Preview or deploy the isolated Phase 2 fixture objects after approval."""

from __future__ import annotations

import argparse
import hashlib
from io import StringIO
from zipfile import ZipFile

from snowflake.connector.util_text import split_statements

from quakewatch.raw_load import connect_project
from scripts.fixtures.build_phase2_fixture_bundle import DEFAULT_OUTPUT
from scripts.fixtures.phase2_fixture_namespace import (
    SQL_FILES,
    TEST_DATABASE,
    inputs,
    validate_and_rewrite,
)

BUNDLE = DEFAULT_OUTPUT / "quakewatch_procedure.zip"
BUNDLE_SHA256 = "4139966c9938702f341a72793d3da01cb931c8aad4d999fc75760a2741f00b15"
STAGE = f"@{TEST_DATABASE}.RAW.USGS_JSON_STAGE/procedure"
PACKAGE_CHECK_SQL = f"""
SELECT COUNT(*) FROM {TEST_DATABASE}.INFORMATION_SCHEMA.PACKAGES
WHERE PACKAGE_NAME = 'snowflake-snowpark-python'
  AND VERSION = '1.55.0' AND LANGUAGE = 'python' AND RUNTIME_VERSION = '3.12'
"""


def ddl_statements() -> tuple[str, ...]:
    """Reject stale generated SQL and the procedure ZIP before any connection."""
    if not BUNDLE.is_file() or hashlib.sha256(BUNDLE.read_bytes()).hexdigest() != BUNDLE_SHA256:
        raise ValueError("test-only procedure ZIP missing or differs from reviewed SHA-256")
    with ZipFile(BUNDLE) as archive:
        if any(
            b"QUAKEWATCH.RAW." in archive.read(name) or b"QUAKEWATCH.CURATED." in archive.read(name)
            for name in archive.namelist()
        ):
            raise ValueError("production database reference in fixture ZIP")
    sources = inputs()
    statements = []
    for name in SQL_FILES:
        relative = f"sql/{name}"
        expected, _count = validate_and_rewrite(relative, sources[relative])
        path = DEFAULT_OUTPUT / relative
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            raise ValueError(f"generated fixture SQL missing or stale: {relative}")
        statements.extend(
            statement.strip()
            for statement, _ in split_statements(StringIO(expected), remove_comments=True)
            if statement.strip()
        )
    return tuple(statements)


def _guard_empty(cursor) -> None:
    for command in (
        f"SHOW TABLES IN SCHEMA {TEST_DATABASE}.RAW",
        f"SHOW STAGES IN SCHEMA {TEST_DATABASE}.RAW",
        f"SHOW TABLES IN SCHEMA {TEST_DATABASE}.CURATED",
        f"SHOW VIEWS IN SCHEMA {TEST_DATABASE}.CURATED",
        f"SHOW USER PROCEDURES IN SCHEMA {TEST_DATABASE}.CURATED",
    ):
        cursor.execute(command)
        if cursor.fetchall():
            raise RuntimeError(f"fixture schema is not empty: {command}")


def _guard_package(cursor) -> None:
    cursor.execute(PACKAGE_CHECK_SQL)
    if cursor.fetchone()[0] < 1:
        raise RuntimeError("Python 3.12 / Snowpark 1.55.0 is absent from account package catalog")


def preview() -> None:
    statements = ddl_statements()
    print("Phase 2 fixture deployment: preview only; no Snowflake connection")
    print(f"Database: {TEST_DATABASE}; generated SQL statements: {len(statements)}")
    print(f"Reviewed ZIP SHA-256: {BUNDLE_SHA256}")
    print("Live order: empty-schema guard, package check, CREATE STAGE, PUT ZIP, DDL")


def execute_deploy() -> dict:
    """Create isolated test objects once after cost and account-change approval."""
    statements = ddl_statements()
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            _guard_empty(cursor)
            _guard_package(cursor)
            cursor.execute(
                f"CREATE STAGE {TEST_DATABASE}.RAW.USGS_JSON_STAGE FILE_FORMAT = (TYPE = JSON)"
            )
            cursor.execute(f"PUT '{BUNDLE.as_uri()}' {STAGE} AUTO_COMPRESS=FALSE OVERWRITE=FALSE")
            columns = [column[0].lower() for column in cursor.description]
            upload = dict(zip(columns, cursor.fetchone(), strict=True))
            if upload.get("status") != "UPLOADED":
                raise RuntimeError("fixture ZIP was not newly uploaded; inspect stage")
            for statement in statements:
                cursor.execute(statement)
    return {
        "database": TEST_DATABASE,
        "stage_upload": "UPLOADED",
        "ddl_statements_executed": len(statements),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="deploy isolated Snowflake objects")
    args = parser.parse_args()
    if args.execute:
        print(execute_deploy())
    else:
        preview()


if __name__ == "__main__":
    main()
