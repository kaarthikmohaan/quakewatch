"""Preview or read actual per-query Cortex AI credits from Account Usage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.phase4_cortex_evaluate import BRIEFS_PATH
from scripts.phase4_usage import checked_admin_profile


EARLIER_SUCCESSFUL_QUERY_IDS = (
    "01c76fcf-0002-afd6-000e-fef200033b12",
    "01c76fd2-0002-b113-000e-fef200035e4e",
)


def expected_query_ids(path: Path = BRIEFS_PATH) -> list[str]:
    cache = json.loads(path.read_text(encoding="utf-8"))
    ids = list(EARLIER_SUCCESSFUL_QUERY_IDS)
    for result in cache["results"].values():
        if result.get("query_id"):
            ids.append(result["query_id"])
        if result.get("retry", {}).get("query_id"):
            ids.append(result["retry"]["query_id"])
    if len(ids) != 11 or len(set(ids)) != 11:
        raise RuntimeError("expected exactly eleven unique successful Cortex query IDs")
    return ids


def execute() -> dict:
    import snowflake.connector

    ids = expected_query_ids()
    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    with snowflake.connector.connect(**profile, warehouse="QUAKEWATCH_WH") as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_TIMESTAMP()")
            role, warehouse, checked_at = cursor.fetchone()
            if (role, warehouse) != ("ACCOUNTADMIN", "QUAKEWATCH_WH"):
                raise RuntimeError("unexpected billing role or warehouse")
            placeholders = ", ".join(["%s"] * len(ids))
            cursor.execute(
                "SELECT QUERY_ID, MODEL_NAME, FUNCTION_NAME, CREDITS, "
                "METRICS, IS_COMPLETED, START_TIME, END_TIME "
                "FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY "
                f"WHERE QUERY_ID IN ({placeholders}) "
                "ORDER BY START_TIME, QUERY_ID",
                tuple(ids),
            )
            metering_query_id = cursor.sfqid
            columns = [column[0].lower() for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    found = {row["query_id"] for row in rows}
    return {
        "checked_at_utc": str(checked_at),
        "metering_query_id": metering_query_id,
        "expected_query_count": len(ids),
        "returned_rows": len(rows),
        "missing_query_ids": sorted(set(ids) - found),
        "reported_ai_credits": sum(float(row["credits"]) for row in rows),
        "rows": rows,
        "note": "AI credits only. Account Usage may lag; warehouse platform credits are separate.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run approved paid Account Usage query")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True, default=str))
    else:
        ids = expected_query_ids()
        print(f"Preview only: read Cortex usage for {len(ids)} query IDs; no Snowflake connection")
        print("Role: ACCOUNTADMIN; warehouse: QUAKEWATCH_WH; view: CORTEX_AI_FUNCTIONS_USAGE_HISTORY")
        print("Missing recent rows mean Account Usage lag, not zero credits")


if __name__ == "__main__":
    main()
