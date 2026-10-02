"""Preview or run the reviewed, guarded fixture-database setup once."""

from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

from snowflake.connector.util_text import split_statements

from scripts.evidence.phase2.fixture_name_check import admin_params, name_occupied
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE
from scripts.pipeline.build_procedure_bundle import REPO_ROOT

SETUP_FILE = REPO_ROOT / "sql" / "demos/fixture_setup.sql"
EXPECTED = (
    "USE ROLE ACCOUNTADMIN",
    f"CREATE DATABASE {TEST_DATABASE}",
    f"CREATE SCHEMA {TEST_DATABASE}.RAW",
    f"CREATE SCHEMA {TEST_DATABASE}.CURATED",
    f"GRANT USAGE ON DATABASE {TEST_DATABASE} TO ROLE QUAKEWATCH_ROLE",
    f"GRANT USAGE ON SCHEMA {TEST_DATABASE}.RAW TO ROLE QUAKEWATCH_ROLE",
    f"GRANT USAGE ON SCHEMA {TEST_DATABASE}.CURATED TO ROLE QUAKEWATCH_ROLE",
    f"GRANT CREATE TABLE ON SCHEMA {TEST_DATABASE}.RAW TO ROLE QUAKEWATCH_ROLE",
    f"GRANT CREATE STAGE ON SCHEMA {TEST_DATABASE}.RAW TO ROLE QUAKEWATCH_ROLE",
    f"GRANT CREATE TABLE ON SCHEMA {TEST_DATABASE}.CURATED TO ROLE QUAKEWATCH_ROLE",
    f"GRANT CREATE VIEW ON SCHEMA {TEST_DATABASE}.CURATED TO ROLE QUAKEWATCH_ROLE",
    f"GRANT CREATE PROCEDURE ON SCHEMA {TEST_DATABASE}.CURATED TO ROLE QUAKEWATCH_ROLE",
)


def setup_statements() -> tuple[str, ...]:
    """Stop if the reviewed setup file changes before execution."""
    parsed = tuple(
        statement.strip().rstrip(";").strip()
        for statement, _ in split_statements(
            StringIO(SETUP_FILE.read_text(encoding="utf-8")), remove_comments=True
        )
        if statement.strip()
    )
    if parsed != EXPECTED:
        raise ValueError("fixture setup SQL differs from the reviewed statement list")
    return parsed


def _schema_names(cursor) -> set[str]:
    cursor.execute(f"SHOW SCHEMAS IN DATABASE {TEST_DATABASE}")
    columns = [column[0].lower() for column in cursor.description]
    index = columns.index("name")
    return {str(row[index]).upper() for row in cursor.fetchall()}


def execute_setup(config_path: Path) -> dict:
    """Create the test database once after separate owner cost/change approval."""
    import snowflake.connector

    statements = setup_statements()
    with snowflake.connector.connect(**admin_params(config_path)) as connection:
        with connection.cursor() as cursor:
            if name_occupied(cursor):
                raise RuntimeError("fixture database name is occupied; no setup SQL ran")
            for statement in statements:
                cursor.execute(statement)
            if not name_occupied(cursor) or not {"RAW", "CURATED"} <= _schema_names(cursor):
                raise RuntimeError("setup ran but fixture database/schema verification failed")
    return {
        "database": TEST_DATABASE,
        "schemas": ["RAW", "CURATED"],
        "statements_executed": len(statements),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="make the approved account change")
    args = parser.parse_args()
    if args.execute:
        print(execute_setup(Path.home() / ".snowflake" / "config.toml"))
    else:
        statements = setup_statements()
        print("Phase 2 fixture setup: preview only; no Snowflake connection")
        print(f"Database: {TEST_DATABASE}; reviewed SQL statements: {len(statements)}")
        print("Live mode rechecks exact name, creates database/schemas, grants project role")


if __name__ == "__main__":
    main()
