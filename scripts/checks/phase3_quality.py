"""Preview or deploy Phase 3 health views and run bounded quality queries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from quakewatch.raw_load import connect_project

ROOT = Path(__file__).resolve().parents[2] / "sql"
FILES = (
    ("phase3_health_views.sql", "ba25e6344e812ee6fb052855f0121e20809f5d6fc4d4a335d58c6b18d9486320", 3),
    ("phase3_reconciliation.sql", "8d1b4f2dac5309d06f0d20b6b664f59efa4d288f2a7d88f378b98ff59b49bdf3", 3),
    ("phase3_sample_analysis.sql", "1c948e2ee5d23589e4f5e49665f28f104ad08a7d4dec1ae3e49c03572e717daa", 1),
)
VIEW_NAMES = ("V_BATCH_HEALTH", "V_RECEIPT_WINDOW_AUDIT", "V_EVENT_REJECTS")


def view_action(rows: list[tuple[str, str | None]], views: tuple[str, ...]) -> str:
    """Create absent views, or reuse only a complete exact-definition set."""
    if not rows:
        return "create"
    expected = {name: hashlib.sha256(statement.encode()).hexdigest()
                for name, statement in zip(VIEW_NAMES, views)}
    observed = {name: hashlib.sha256((definition or "").encode()).hexdigest()
                for name, definition in rows}
    if observed != expected:
        raise RuntimeError("Phase 3 views are partial or differ from reviewed SQL; inspect before changing them")
    return "reuse"


def reviewed_sql() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    groups = []
    for name, expected_hash, expected_count in FILES:
        content = (ROOT / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError(f"{name} changed; review before a live run")
        body = "\n".join(line for line in content.decode("utf-8").splitlines()
                         if not line.lstrip().startswith("--"))
        statements = tuple(item.strip() for item in body.split(";") if item.strip())
        if len(statements) != expected_count:
            raise ValueError(f"{name} statement count differs")
        groups.append(statements)
    views, reconciliation, sample = groups
    if (any(not stmt.startswith(f"CREATE VIEW QUAKEWATCH.CURATED.{name} AS")
            for stmt, name in zip(views, VIEW_NAMES))
            or any(not stmt.startswith("SELECT ") for stmt in (*reconciliation, *sample))):
        raise ValueError("reviewed Phase 3 statement targets differ")
    return views, reconciliation, sample


def execute_quality() -> dict:
    views, reconciliation, sample = reviewed_sql()
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            cursor.execute("""
                SELECT TABLE_NAME, VIEW_DEFINITION
                FROM QUAKEWATCH.INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = 'CURATED'
                  AND TABLE_NAME IN ('V_BATCH_HEALTH', 'V_RECEIPT_WINDOW_AUDIT',
                                     'V_EVENT_REJECTS')
            """)
            action = view_action(cursor.fetchall(), views)
            if action == "create":
                for statement in views:
                    cursor.execute(statement)
            cursor.execute(reconciliation[0])
            health_summary = [tuple(row) for row in cursor.fetchall()]
            counts = []
            for statement in reconciliation[1:]:
                cursor.execute(f"SELECT COUNT(*) FROM ({statement}) AS QUALITY_ANOMALIES")
                counts.append(int(cursor.fetchone()[0]))
            cursor.execute(sample[0])
            sample_rows = [tuple(row) for row in cursor.fetchall()]
    return {"views_created": list(VIEW_NAMES) if action == "create" else [],
            "views_reused": list(VIEW_NAMES) if action == "reuse" else [],
            "health_summary": health_summary,
            "batch_anomaly_rows": counts[0], "window_anomaly_rows": counts[1],
            "sample_rows": sample_rows,
            "status": "pass" if counts == [0, 0] else "review"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run paid Snowflake DDL and SELECTs")
    args = parser.parse_args()
    if args.execute:
        result = execute_quality()
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        if result["status"] != "pass":
            raise SystemExit(1)
    else:
        reviewed_sql()
        print("Phase 3 quality: preview only; no Snowflake connection")
        print("Three new health views, three reconciliation queries, one bounded sample query")
        print("Existing views are reused only when all three definitions match exactly")


if __name__ == "__main__":
    main()
