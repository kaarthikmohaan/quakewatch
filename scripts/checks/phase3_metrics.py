"""Preview or measure first-backfill latency and source freshness in Snowflake."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from quakewatch.raw_load import connect_project

SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "phase3_metrics.sql"
EXPECTED_SHA256 = "1a0390820a23bbe6043e3dba8fb27db2f86aa6e8205f83dac44f9e2e4891da3d"
TARGET_P95_SECONDS = 86_400


def reviewed_statements() -> tuple[str, str]:
    content = SQL_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Phase 3 metrics SQL changed; review before a live run")
    body = "\n".join(line for line in content.decode().splitlines()
                     if not line.lstrip().startswith("--"))
    statements = tuple(item.strip() for item in body.split(";") if item.strip())
    if len(statements) != 2 or any(not item.startswith("SELECT ") for item in statements):
        raise ValueError("Phase 3 metrics statement count or type differs")
    return statements


def measure() -> dict:
    statements = reviewed_statements()
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            cursor.execute(statements[0])
            latency = tuple(cursor.fetchone())
            latency_query_id = cursor.sfqid
            cursor.execute(statements[1])
            freshness = tuple(cursor.fetchone())
            freshness_query_id = cursor.sfqid
    return {
        "target_p95_seconds": TARGET_P95_SECONDS,
        "sample_attempts": latency[0],
        "requested_range": [latency[1], latency[2]],
        "fetch_to_curated_range": [latency[3], latency[4]],
        "latency_seconds": {"min": latency[5], "p50": latency[6],
                            "p95": latency[7], "max": latency[8]},
        "target_met": latency[0] >= 30 and latency[7] is not None
                      and latency[7] <= TARGET_P95_SECONDS,
        "freshness": {"last_successful_fetch": freshness[0],
                      "last_successful_fetch_age_seconds": freshness[1],
                      "newest_accepted_source_update": freshness[2],
                      "newest_accepted_source_age_seconds": freshness[3]},
        "query_ids": [latency_query_id, freshness_query_id],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(measure(), indent=2, sort_keys=True, default=str))
    else:
        reviewed_statements()
        print("Preview only: two read-only Snowflake SELECTs; no connection")
        print("Sample: five-year origin attempts, including one overlapping sample")
        print("Predeclared target: p95 fetch-to-curated <= 24 hours; at least 30 attempts")


if __name__ == "__main__":
    main()
