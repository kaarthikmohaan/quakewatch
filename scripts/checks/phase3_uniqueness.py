"""Preview or run the two read-only Phase 3 model-grain checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from quakewatch.raw_load import connect_project


SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "phase3_uniqueness.sql"
EXPECTED_SHA256 = "fedad6f0cff3da90f86e974bd3bc939552da4a540ccd4786a8e632a12821eb45"
CHECKS = ("revision_duplicate_groups", "bridge_duplicate_groups")
TABLES = ("QUAKEWATCH.CURATED.FACT_EVENT_REVISION",
          "QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE")


def reviewed_statements() -> tuple[str, str]:
    content = SQL_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Phase 3 uniqueness SQL changed; review it before a live run")
    sql = "\n".join(line for line in content.decode("utf-8").splitlines()
                    if not line.lstrip().startswith("--"))
    statements = tuple(item.strip() for item in sql.split(";") if item.strip())
    if (len(statements) != 2
            or any(not item.startswith("SELECT ") for item in statements)
            or any(table not in statement for table, statement in zip(TABLES, statements))):
        raise ValueError("reviewed uniqueness statements differ")
    return statements


def execute_checks() -> dict:
    statements = reviewed_statements()
    counts = {}
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            for name, statement in zip(CHECKS, statements):
                cursor.execute(f"SELECT COUNT(*) FROM ({statement}) AS DUPLICATE_GROUPS")
                counts[name] = int(cursor.fetchone()[0])
    return {"status": "pass" if all(value == 0 for value in counts.values()) else "fail",
            "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run two paid Snowflake SELECTs")
    args = parser.parse_args()
    if args.execute:
        result = execute_checks()
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["status"] != "pass":
            raise SystemExit(1)
    else:
        reviewed_statements()
        print("Phase 3 uniqueness: preview only; no Snowflake connection")
        print("Target: QUAKEWATCH.CURATED; two SELECT-only duplicate-group checks")
        print("Expected: zero revision duplicate groups and zero bridge duplicate groups")


if __name__ == "__main__":
    main()
