"""Read-only live quality and analysis checks for the QuakeWatch demo."""

import json
from pathlib import Path

import snowflake.connector

from scripts.checks.phase3_quality import reviewed_sql
from scripts.checks.phase3_uniqueness import CHECKS, reviewed_statements
from scripts.checks.phase4_usage import checked_admin_profile


def show(label, value):
    print(json.dumps({label: value}, default=str, sort_keys=True), flush=True)


def main():
    _views, reconciliation, sample = reviewed_sql()
    uniqueness = reviewed_statements()
    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    profile["role"] = "QUAKEWATCH_ROLE"
    with snowflake.connector.connect(**profile, warehouse="QUAKEWATCH_WH") as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("Unexpected role or warehouse")
            cursor.execute(reconciliation[0])
            show("batch_health", cursor.fetchall())
            for name, query in zip(("batch_anomalies", "window_anomalies"), reconciliation[1:]):
                cursor.execute(f"SELECT COUNT(*) FROM ({query}) AS ANOMALIES")
                show(name, int(cursor.fetchone()[0]))
            for name, query in zip(CHECKS, uniqueness):
                cursor.execute(f"SELECT COUNT(*) FROM ({query}) AS DUPLICATES")
                show(name, int(cursor.fetchone()[0]))
            cursor.execute(sample[0])
            show("seattle_sample", cursor.fetchall())
            cursor.execute(Path("sql/phase4_cortex_aggregates.sql").read_text())
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if len(rows) != 10:
                raise RuntimeError("Expected exactly ten public-site cases")
            show("ten_case_event_counts", {row["CASE_ID"]: row["EVENT_COUNT"] for row in rows})


if __name__ == "__main__":
    main()
