"""Live integration check: compile every SQL statement against Snowflake, then run read-only checks.

Preview by default; nothing connects. With ``--execute`` (uses a little warehouse
time) it runs as ``QUAKEWATCH_ROLE`` and:

1. compiles every SQL statement the Snowpark procedure issues, and every reviewed
   check and analysis query, with ``EXPLAIN``. EXPLAIN plans a statement against
   the live tables without running it, so a renamed column or table fails here
   without any data being read or changed;
2. confirms the deployed procedure exists;
3. runs the read-only post-run and uniqueness checks and requires both to pass.

It does not call the procedure, because that writes to the warehouse. CI runs it
through the manually triggered integration workflow.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import re
from contextlib import nullcontext

import quakewatch
from quakewatch.raw_load import connect_project
from scripts.checks import postrun, uniqueness
from scripts.pipeline.procedure_deploy import SQL_DIR, sql_statements

READ_ONLY_SQL_DIRS = ("checks", "analysis")
PROCEDURE = "PROCESS_LOADED_ATTEMPT"

# EXPLAIN needs concrete values in place of bind markers.
BIND_STAND_INS = (
    (re.compile(r"PARSE_JSON\(\?\)"), "PARSE_JSON('[]')"),
    (re.compile(r"TO_TIMESTAMP_TZ\(\?\)"), "TO_TIMESTAMP_TZ('2000-01-01T00:00:00Z')"),
    (re.compile(r"\?"), "NULL"),
)


def procedure_statements() -> dict[str, str]:
    """Every module-level *_SQL constant in the Snowpark modules, keyed by module.NAME."""
    found = {}
    for info in pkgutil.iter_modules(quakewatch.__path__):
        if not info.name.startswith("snowpark_"):
            continue
        module = importlib.import_module(f"quakewatch.{info.name}")
        for name, value in vars(module).items():
            if name.endswith("_SQL") and isinstance(value, str):
                found[f"{info.name}.{name}"] = value
    return found


def file_statements() -> dict[str, str]:
    found = {}
    for folder in READ_ONLY_SQL_DIRS:
        for path in sorted((SQL_DIR / folder).glob("*.sql")):
            for number, statement in enumerate(sql_statements(path), start=1):
                if re.match(r"(?is)^\s*(SELECT|WITH)\b", statement):
                    found[f"{path.relative_to(SQL_DIR)}#{number}"] = statement
    return found


def explainable(sql: str) -> str:
    for pattern, value in BIND_STAND_INS:
        sql = pattern.sub(value, sql)
    return "EXPLAIN USING TEXT " + sql.strip().rstrip(";")


def compile_all(cursor, statements: dict[str, str]) -> list[str]:
    failures = []
    for label, sql in statements.items():
        try:
            cursor.execute(explainable(sql))
            cursor.fetchall()
        except Exception as exc:  # report every failure, not just the first
            detail = " / ".join(line.strip() for line in str(exc).splitlines() if line.strip())
            failures.append(f"{label}: {type(exc).__name__}: {detail}")
    return failures


def preview() -> None:
    procedure, files = procedure_statements(), file_statements()
    print("Integration check: preview only; no Snowflake connection")
    print(
        f"Would compile {len(procedure)} procedure statements and {len(files)} reviewed queries with EXPLAIN"
    )
    print(f"Then confirm {PROCEDURE} exists and run the read-only post-run and uniqueness checks")


def execute() -> dict:
    statements = {**procedure_statements(), **file_statements()}
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            failures = compile_all(cursor, statements)
            cursor.execute(f"SHOW USER PROCEDURES LIKE '{PROCEDURE}' IN SCHEMA QUAKEWATCH.CURATED")
            procedure_found = bool(cursor.fetchall())
        # Reuse this connection so a local run prompts for the passphrase once.
        shared = lambda: nullcontext(connection)  # noqa: E731
        postrun.connect_project = shared
        uniqueness.connect_project = shared
        postrun_result = postrun.postrun()
        uniqueness_result = uniqueness.execute_checks()
    ok = (
        not failures
        and procedure_found
        and postrun_result.get("status") == "pass"
        and uniqueness_result.get("status") == "pass"
    )
    return {
        "status": "pass" if ok else "fail",
        "statements_compiled": len(statements) - len(failures),
        "compile_failures": failures,
        "procedure_found": procedure_found,
        "postrun_status": postrun_result.get("status"),
        "uniqueness_status": uniqueness_result.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Live, read-only integration check")
    parser.add_argument(
        "--execute", action="store_true", help="connect and run (uses warehouse credits)"
    )
    args = parser.parse_args()
    if not args.execute:
        preview()
        return
    result = execute()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
