"""Read-only account metering snapshot for the QuakeWatch warehouse."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

WAREHOUSE = "QUAKEWATCH_WH"
START_UTC = "2026-10-01 08:00:00 +00:00"
END_UTC = "2026-10-01 12:00:00 +00:00"


def checked_admin_profile(config_path: Path) -> dict:
    """Use the existing local billing-capable profile; never print secrets."""
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    profile = config["connections"]["quakewatch_admin"]
    if profile.get("role") != "ACCOUNTADMIN" or any(
        not profile.get(key) for key in ("account", "user", "password")
    ):
        raise RuntimeError("local account billing profile is missing or unexpected")
    return {key: profile[key] for key in ("account", "user", "password", "role")}


def execute() -> dict:
    import snowflake.connector

    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    with snowflake.connector.connect(**profile, warehouse=WAREHOUSE) as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET TIMEZONE = 'UTC'")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_TIMESTAMP()")
            role, warehouse, checked_at = cursor.fetchone()
            if role != "ACCOUNTADMIN" or warehouse != WAREHOUSE:
                raise RuntimeError("unexpected billing role or warehouse")
            cursor.execute("""
                SELECT START_TIME, END_TIME, CREDITS_USED_COMPUTE,
                       CREDITS_USED_CLOUD_SERVICES, CREDITS_USED
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                WHERE WAREHOUSE_NAME = 'QUAKEWATCH_WH'
                  AND START_TIME >= TO_TIMESTAMP_TZ(%s)
                  AND START_TIME < TO_TIMESTAMP_TZ(%s)
                ORDER BY START_TIME
            """, (START_UTC, END_UTC))
            query_id = cursor.sfqid
            hours = [
                {"start_utc": str(start), "end_utc": str(end),
                 "compute_credits": float(compute),
                 "cloud_services_credits": float(cloud),
                 "reported_credits": float(total)}
                for start, end, compute, cloud, total in cursor.fetchall()
            ]
            return {"checked_at_utc": str(checked_at), "warehouse": WAREHOUSE,
                    "window_start_utc": START_UTC, "window_end_utc": END_UTC,
                    "metering_query_id": query_id, "hours": hours,
                    "note": "Account Usage can lag; warehouse hours include any other activity and are not a per-drill bill."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run approved paid account-usage query")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        print("Phase 4 metering preview only; no Snowflake connection")
        print(f"Read {WAREHOUSE} hourly usage from {START_UTC} to {END_UTC}")
        print("Account Usage may lag up to three hours; no missing hour is interpreted as zero")


if __name__ == "__main__":
    main()
