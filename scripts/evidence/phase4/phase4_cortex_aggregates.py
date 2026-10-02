"""Preview or save ten bounded public-site SQL aggregates for Cortex review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.checks.phase4_usage import checked_admin_profile

ROOT = Path(__file__).resolve().parents[3]
SQL_PATH = ROOT / "sql" / "phase4_cortex_aggregates.sql"
OUTPUT_PATH = ROOT / "data" / "cortex" / "phase4_aggregates.json"
EXPECTED_CASES = {
    "seattle-2022", "sf-2022", "anchorage-2022",
    "seattle-2024", "sf-2024", "anchorage-2024",
    "seattle-2026", "sf-2026", "anchorage-2026", "seattle-day",
}


def read_sql() -> str:
    sql = SQL_PATH.read_text(encoding="utf-8")
    if not sql.lstrip().startswith("-- REVIEW ONLY."):
        raise RuntimeError("aggregate SQL review marker is missing")
    return sql


def save_aggregates(columns: list[str], rows: list[tuple], query_id: str,
                    sql: str, output_path: Path = OUTPUT_PATH) -> dict:
    records = [dict(zip(columns, row)) for row in rows]
    case_ids = [record["CASE_ID"] for record in records]
    if len(records) != 10 or set(case_ids) != EXPECTED_CASES:
        raise RuntimeError("aggregate query did not return the ten expected cases")
    for record in records:
        if record["SITE_KEY"] not in {"seattle", "san-francisco", "anchorage"}:
            raise RuntimeError("unexpected site in aggregate output")
        if record["RADIUS_KM"] != 250 or record["DISTINCT_RADII"] != 1:
            raise RuntimeError("public site radius is missing or inconsistent")
        if record["EVENT_COUNT"] < 0:
            raise RuntimeError("negative aggregate count")
        if record["EVENT_COUNT"] == 0 and record["NEAREST_EVENT_ID"] is not None:
            raise RuntimeError("zero-count case unexpectedly has nearest event")
        if record["EVENT_COUNT"] > 0 and record["NEAREST_EVENT_ID"] is None:
            raise RuntimeError("nonzero-count case has no nearest event")
        record["INPUT_SHA256"] = hashlib.sha256(
            json.dumps(record, sort_keys=True, default=str).encode()
        ).hexdigest()
    document = {
        "source": "QUAKEWATCH.CURATED.EVENT_CURRENT and BRIDGE_EVENT_SITE",
        "query_id": query_id,
        "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "case_count": len(records),
        "coverage_note": "Modeled warehouse rows; unresolved source gaps and update sweep remain open.",
        "cases": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True, default=str) + "\n",
                           encoding="utf-8")
    return document


def execute() -> dict:
    import snowflake.connector

    sql = read_sql()
    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    profile["role"] = "QUAKEWATCH_ROLE"
    with snowflake.connector.connect(**profile, warehouse="QUAKEWATCH_WH") as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("unexpected project role or warehouse")
            cursor.execute(sql)
            query_id = cursor.sfqid
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
    return save_aggregates(columns, rows, query_id, sql)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run approved paid warehouse query")
    args = parser.parse_args()
    if args.execute:
        document = execute()
        print(json.dumps({
            "status": "saved",
            "path": str(OUTPUT_PATH),
            "case_count": document["case_count"],
            "query_id": document["query_id"],
            "sql_sha256": document["sql_sha256"],
            "event_counts": {case["CASE_ID"]: case["EVENT_COUNT"]
                             for case in document["cases"]},
            "coverage_note": document["coverage_note"],
        }, indent=2, sort_keys=True))
    else:
        sql = read_sql()
        print("Preview only: 10 bounded public-site aggregates; no Snowflake connection")
        print(f"Role: QUAKEWATCH_ROLE; warehouse: QUAKEWATCH_WH; SQL SHA-256: {hashlib.sha256(sql.encode()).hexdigest()}")
        print(f"Output if approved: {OUTPUT_PATH} (ignored by Git)")


if __name__ == "__main__":
    main()
