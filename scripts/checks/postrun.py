"""Read-only aggregate quality and reject-reason check after history processing."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.checks.quality import reviewed_sql, view_action
from scripts.checks.uniqueness import CHECKS, reviewed_statements

VIEW_SQL = """
SELECT TABLE_NAME, VIEW_DEFINITION
FROM QUAKEWATCH.INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'CURATED'
  AND TABLE_NAME IN ('V_BATCH_HEALTH', 'V_RECEIPT_WINDOW_AUDIT', 'V_EVENT_REJECTS')
"""
REJECT_SQL = """
SELECT REJECT_REASON, COUNT(*)
FROM QUAKEWATCH.CURATED.V_EVENT_REJECTS
GROUP BY REJECT_REASON
ORDER BY COUNT(*) DESC, REJECT_REASON
"""


def postrun() -> dict:
    views, reconciliation, _sample = reviewed_sql()
    uniqueness = reviewed_statements()
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 600")
            cursor.execute(VIEW_SQL)
            if view_action(cursor.fetchall(), views) != "reuse":
                raise RuntimeError("Phase 3 reporting views are absent")
            cursor.execute(reconciliation[0])
            health = [tuple(row) for row in cursor.fetchall()]
            anomaly_counts = []
            for statement in reconciliation[1:]:
                cursor.execute(f"SELECT COUNT(*) FROM ({statement}) AS ANOMALIES")
                anomaly_counts.append(int(cursor.fetchone()[0]))
            duplicate_counts = {}
            for name, statement in zip(CHECKS, uniqueness):
                cursor.execute(f"SELECT COUNT(*) FROM ({statement}) AS DUPLICATES")
                duplicate_counts[name] = int(cursor.fetchone()[0])
            cursor.execute(REJECT_SQL)
            reasons = [(reason, int(count)) for reason, count in cursor.fetchall()]
    health_rejects = sum(int(row[6] or 0) for row in health)
    reported_rejects = sum(count for _, count in reasons)
    return {
        "health_summary": health,
        "batch_anomaly_rows": anomaly_counts[0],
        "window_anomaly_rows": anomaly_counts[1],
        "duplicate_groups": duplicate_counts,
        "reject_reasons": reasons,
        "status": "pass" if (
            len(health) == 1 and health[0][0] == "RECONCILED"
            and anomaly_counts == [0, 0]
            and all(count == 0 for count in duplicate_counts.values())
            and health_rejects == reported_rejects
        ) else "review",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        result = postrun()
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        if result["status"] != "pass":
            raise SystemExit(1)
    else:
        reviewed_sql()
        reviewed_statements()
        print("Preview only: no Snowflake connection")
        print("Read-only health, window reconciliation, uniqueness, and reject reasons")


if __name__ == "__main__":
    main()
