"""Preview or execute an isolated Snowflake current-view fixture check."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.raw_load import connect_project


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "tests" / "fixtures"
VIEW_FILE = ROOT / "sql" / "phase2_revision_current.sql"
TEMP_PREFIX = "QUAKEWATCH.CURATED.QW_CURRENT_FIXTURE_"


def view_select_sql(temp_table: str) -> str:
    """Use the checked-in view's SELECT with only its source table redirected."""
    if not re.fullmatch(r"QUAKEWATCH\.CURATED\.QW_CURRENT_FIXTURE_[0-9A-F]{32}", temp_table):
        raise ValueError("invalid temporary fixture table name")
    source = VIEW_FILE.read_text(encoding="utf-8")
    marker = "CREATE OR REPLACE VIEW QUAKEWATCH.CURATED.EVENT_CURRENT AS\n"
    if source.count(marker) != 1:
        raise ValueError("current-view definition changed; review fixture check")
    query = source.split(marker, 1)[1].strip().rstrip(";")
    target = "FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION"
    if query.count(target) != 1:
        raise ValueError("current-view fact source changed; review fixture check")
    return query.replace(target, f"FROM {temp_table} FACT_EVENT_REVISION")


def feature_row(name: str) -> tuple:
    feature = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    props = feature["properties"]
    payload_hash = hashlib.sha256(json.dumps(
        feature, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    def clock(value: int) -> str:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    return (feature["id"], clock(props["updated"]), payload_hash,
            feature["id"], clock(props["time"]),
            "2026-09-30T00:00:00+00:00", "2026-09-30T00:00:00+00:00",
            props["status"], props["mag"], "1", name, 1)


INSERT_SQL = """INSERT INTO {table} (
    CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SOURCE_EVENT_ID,
    ORIGIN_TIME, FETCHED_AT, CURATED_AT, SOURCE_STATUS, MAGNITUDE,
    STAGING_PARSER_VERSION, STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER
) SELECT %s, TO_TIMESTAMP_TZ(%s), %s, %s,
         TO_TIMESTAMP_TZ(%s), TO_TIMESTAMP_TZ(%s), TO_TIMESTAMP_TZ(%s),
         %s, %s, %s, %s, %s"""


def preview() -> None:
    print("Phase 2 current-view fixture: preview only; no Snowflake connection or changes")
    print("Temporary revision table: original + later update -> current magnitude 1.28")
    print("Add latest deletion -> zero current rows; replay old row -> still zero")
    print("No permanent RAW/curated writes, view replacement, or procedure call")


def _assert_state(cursor, query: str, expected_rows: int, expected_current: list[tuple]) -> None:
    cursor.execute(f"SELECT CANONICAL_EVENT_ID, SOURCE_STATUS, MAGNITUDE FROM ({query})")
    rows = cursor.fetchall()
    if rows != expected_current:
        raise RuntimeError(f"current-view fixture mismatch: {rows!r}")
    # The caller supplies the temporary table as the only source in this query.
    match = re.search(r"FROM (QUAKEWATCH\.CURATED\.QW_CURRENT_FIXTURE_[0-9A-F]{32}) FACT_EVENT_REVISION", query)
    if match is None:
        raise ValueError("view query is not isolated to the temporary table")
    cursor.execute(f"SELECT COUNT(*) FROM {match.group(1)}")
    count = cursor.fetchone()[0]
    if count != expected_rows:
        raise RuntimeError(f"fixture revision count mismatch: {count}")


def execute_fixture() -> dict:
    table = TEMP_PREFIX + uuid.uuid4().hex.upper()
    query = view_select_sql(table)
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            cursor.execute(f"CREATE TEMPORARY TABLE {table} LIKE QUAKEWATCH.CURATED.FACT_EVENT_REVISION")
            for name in ("normal_event.json", "synthetic_revision_event.json"):
                cursor.execute(INSERT_SQL.format(table=table), feature_row(name))
            event_id = "uw714110682"
            _assert_state(cursor, query, 2, [(event_id, "reviewed", 1.28)])
            cursor.execute(INSERT_SQL.format(table=table), feature_row("synthetic_tombstone_event.json"))
            _assert_state(cursor, query, 3, [])
            cursor.execute(INSERT_SQL.format(table=table), feature_row("normal_event.json"))
            _assert_state(cursor, query, 4, [])
            return {"active_revision_magnitude": 1.28,
                    "current_after_tombstone": 0,
                    "current_after_stale_replay": 0,
                    "temporary_revision_rows": 4}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the paid Snowflake fixture check")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_fixture(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
