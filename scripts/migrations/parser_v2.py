"""Deploy staging parser version 2 and relabel the stored stub-record rejects.

Preview by default; nothing connects. With ``--execute`` (uses warehouse
credits) it:

1. checks the stored rows match the offline replay: the expected row count,
   485 ``invalid_origin_time`` rejects that are all USGS stub payloads, and no
   valid row at the ``[0, 0]`` placeholder;
2. in one transaction, relabels exactly those rejects as ``source_stub_record``
   and marks staging and fact rows as parser version 2, then rechecks counts
   and commits, or rolls back on any mismatch;
3. uploads the version 2 procedure bundle and replaces the procedure;
4. creates the update-watermark table if it is absent.

Version 2 changes only the stub-record label and adds the placeholder check,
so marking unchanged rows as version 2 is equivalent to reprocessing them.
Running it again after a successful migration skips step 2.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quakewatch.raw_load import connect_project
from quakewatch.staging import STAGING_PARSER_VERSION
from scripts.pipeline.build_procedure_bundle import DEFAULT_OUTPUT, build_bundle
from scripts.pipeline.procedure_deploy import (
    SQL_DIR,
    STAGE,
    run_sql_file,
    upload_and_create_procedure,
)

EXPECTED_STAGING_ROWS = 216_391
EXPECTED_STUB_ROWS = 485
OLD_VERSION, NEW_VERSION = "1", "2"
OLD_REASON, NEW_REASON = "invalid_origin_time", "source_stub_record"
WATERMARK_SQL = SQL_DIR / "setup/03_update_watermark.sql"

STG = "QUAKEWATCH.CURATED.STG_EVENT_REVISION"
FACT = "QUAKEWATCH.CURATED.FACT_EVENT_REVISION"
RAW = "QUAKEWATCH.RAW.RAW_EVENT_RECORDS"

# A USGS stub feature has no origin time, magnitude, or status (JSON null or absent).
STUB_CONDITION = " AND ".join(
    f"(r.PAYLOAD:properties:{key} IS NULL OR IS_NULL_VALUE(r.PAYLOAD:properties:{key}))"
    for key in ("time", "mag", "status")
)
RAW_JOIN = (
    "r.ATTEMPT_ID = s.ATTEMPT_ID AND r.STAGE_FILE_NAME = s.STAGE_FILE_NAME "
    "AND r.STAGE_FILE_ROW_NUMBER = s.STAGE_FILE_ROW_NUMBER"
)

STATE_SQL = (
    f"SELECT STAGING_PARSER_VERSION, REJECT_REASON, COUNT(*) FROM {STG} GROUP BY 1, 2 ORDER BY 1, 2"
)
STUB_SQL = (
    f"SELECT COUNT(*) FROM {STG} s JOIN {RAW} r ON {RAW_JOIN} "
    f"WHERE s.REJECT_REASON = %s AND {STUB_CONDITION}"
)
PLACEHOLDER_SQL = (
    f"SELECT COUNT(*) FROM {STG} WHERE REJECT_REASON IS NULL AND LONGITUDE = 0 AND LATITUDE = 0"
)
FACT_STATE_SQL = f"SELECT STAGING_PARSER_VERSION, COUNT(*) FROM {FACT} GROUP BY 1 ORDER BY 1"
RELABEL_SQL = (
    f"UPDATE {STG} s SET REJECT_REASON = %s FROM {RAW} r "
    f"WHERE {RAW_JOIN} AND s.REJECT_REASON = %s AND {STUB_CONDITION}"
)
STG_VERSION_SQL = f"UPDATE {STG} SET STAGING_PARSER_VERSION = %s WHERE STAGING_PARSER_VERSION = %s"
FACT_VERSION_SQL = (
    f"UPDATE {FACT} SET STAGING_PARSER_VERSION = %s WHERE STAGING_PARSER_VERSION = %s"
)


def expected_state(version: str, reason: str) -> dict:
    return {
        (version, None): EXPECTED_STAGING_ROWS - EXPECTED_STUB_ROWS,
        (version, reason): EXPECTED_STUB_ROWS,
    }


def _scalar(cursor, sql: str, params: tuple = ()) -> int:
    cursor.execute(sql, params) if params else cursor.execute(sql)
    return int(cursor.fetchone()[0])


def _state(cursor) -> dict:
    cursor.execute(STATE_SQL)
    return {(version, reason): int(count) for version, reason, count in cursor.fetchall()}


def _fact_state(cursor) -> dict:
    cursor.execute(FACT_STATE_SQL)
    return {version: int(count) for version, count in cursor.fetchall()}


def migrate(cursor) -> str:
    """Relabel stub rejects and mark rows as version 2; return what happened."""
    state = _state(cursor)
    if state == expected_state(NEW_VERSION, NEW_REASON) and set(_fact_state(cursor)) == {
        NEW_VERSION
    }:
        return "already migrated"
    if state != expected_state(OLD_VERSION, OLD_REASON):
        raise RuntimeError(f"staging state differs from the offline replay: {state}")
    if _scalar(cursor, STUB_SQL, (OLD_REASON,)) != EXPECTED_STUB_ROWS:
        raise RuntimeError("not every invalid_origin_time reject is a USGS stub payload")
    if _scalar(cursor, PLACEHOLDER_SQL) != 0:
        raise RuntimeError("a valid stored row sits at [0, 0]; version 2 would reject it")
    facts = _fact_state(cursor)
    if set(facts) != {OLD_VERSION}:
        raise RuntimeError(f"fact parser versions are not all {OLD_VERSION}: {facts}")

    cursor.execute("BEGIN")
    try:
        cursor.execute(RELABEL_SQL, (NEW_REASON, OLD_REASON))
        if cursor.rowcount != EXPECTED_STUB_ROWS:
            raise RuntimeError(f"relabelled {cursor.rowcount} rows, expected {EXPECTED_STUB_ROWS}")
        cursor.execute(STG_VERSION_SQL, (NEW_VERSION, OLD_VERSION))
        if cursor.rowcount != EXPECTED_STAGING_ROWS:
            raise RuntimeError(
                f"versioned {cursor.rowcount} staging rows, expected {EXPECTED_STAGING_ROWS}"
            )
        cursor.execute(FACT_VERSION_SQL, (NEW_VERSION, OLD_VERSION))
        if cursor.rowcount != facts[OLD_VERSION]:
            raise RuntimeError(f"versioned {cursor.rowcount} facts, expected {facts[OLD_VERSION]}")
        if _state(cursor) != expected_state(NEW_VERSION, NEW_REASON):
            raise RuntimeError("post-migration staging state does not match")
        cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    return f"relabelled {EXPECTED_STUB_ROWS} rejects; versioned {EXPECTED_STAGING_ROWS} staging rows and {facts[OLD_VERSION]} facts"


def deploy(cursor, bundle: Path) -> None:
    upload_and_create_procedure(cursor, bundle)
    run_sql_file(cursor, WATERMARK_SQL)


def preview() -> None:
    print("Parser version 2 release: preview only; no Snowflake connection or changes")
    print(f"Local parser version: {STAGING_PARSER_VERSION}")
    print(
        f"Expects {EXPECTED_STAGING_ROWS:,} staging rows, {EXPECTED_STUB_ROWS} of them "
        f"'{OLD_REASON}' rejects that are USGS stub payloads"
    )
    print(f"Then: relabel to '{NEW_REASON}' and mark rows version {NEW_VERSION} in one transaction")
    print(f"Then: upload {DEFAULT_OUTPUT.name} to {STAGE} and replace the procedure")
    print("Then: create QUAKEWATCH.RAW.UPDATE_WATERMARK if absent")


def execute() -> dict:
    if STAGING_PARSER_VERSION != NEW_VERSION:
        raise RuntimeError(f"local parser is version {STAGING_PARSER_VERSION}, not {NEW_VERSION}")
    digest = build_bundle(DEFAULT_OUTPUT)
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            migration = migrate(cursor)
            deploy(cursor, DEFAULT_OUTPUT)
            state = {
                f"{version}/{reason}": count for (version, reason), count in _state(cursor).items()
            }
    return {"migration": migration, "bundle_sha256": digest, "staging_state": state}


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy parser version 2 and relabel stub rejects")
    parser.add_argument(
        "--execute", action="store_true", help="connect and run (uses warehouse credits)"
    )
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        preview()


if __name__ == "__main__":
    main()
