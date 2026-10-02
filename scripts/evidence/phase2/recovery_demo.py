"""Preview or run a guarded failed-transform/retry drill in the fixture database.

The source attempt has already been loaded and processed. This drill proves that
a later failed processing invocation rolls back and can be retried from RAW;
it does not represent a first-ever processing failure for that attempt.
"""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.fixture_original import ATTEMPT_ID, CURATED, RAW
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE

DEMO_PROCEDURE = f"{CURATED}.PROCESS_LOADED_ATTEMPT_FAILURE_DEMO"
FAILURE_TEXT = "intentional fixture transform failure after model writes"
CREATE_SQL = f"""
CREATE PROCEDURE {DEMO_PROCEDURE}(ATTEMPT_ID VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.12'
PACKAGES = ('snowflake-snowpark-python==1.55.0')
IMPORTS = ('@{TEST_DATABASE}.RAW.USGS_JSON_STAGE/procedure/quakewatch_procedure.zip')
HANDLER = 'run'
EXECUTE AS OWNER
AS
$$
import json
from quakewatch.process_transaction import process_loaded_attempt
from quakewatch.snowpark_alias_read import resolve_durable_aliases
from quakewatch.snowpark_model_writer import SnowparkModelWriter

class FailAfterWrites(SnowparkModelWriter):
    def write_models(self, session, projection):
        super().write_models(session, projection)
        raise ValueError({FAILURE_TEXT!r})

def run(session, attempt_id):
    try:
        process_loaded_attempt(session, attempt_id,
                               FailAfterWrites(resolve_durable_aliases))
    except ValueError as error:
        if str(error) != {FAILURE_TEXT!r}:
            raise
        return json.dumps({{"status": "failed_as_planned", "attempt_id": attempt_id}})
    raise RuntimeError("failure drill unexpectedly completed")
$$
"""


def _count(cursor, table: str, where: str = "", params: tuple = ()) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {table} {where}", params)
    return int(cursor.fetchone()[0])


def _snapshot(cursor, attempt_id: str = ATTEMPT_ID) -> dict[str, int]:
    return {
        "raw": _count(cursor, f"{RAW}.RAW_EVENT_RECORDS", "WHERE ATTEMPT_ID = %s", (attempt_id,)),
        "receipts": _count(cursor, f"{RAW}.BATCH_ATTEMPT", "WHERE ATTEMPT_ID = %s", (attempt_id,)),
        "staging": _count(cursor, f"{CURATED}.STG_EVENT_REVISION"),
        "revisions": _count(cursor, f"{CURATED}.FACT_EVENT_REVISION"),
        "bridges": _count(cursor, f"{CURATED}.BRIDGE_EVENT_SITE"),
        "batches": _count(cursor, f"{CURATED}.FACT_BATCH_RUN"),
        "sites": _count(cursor, f"{CURATED}.DIM_SITE"),
        "dates": _count(cursor, f"{CURATED}.DIM_DATE"),
        "magnitude_types": _count(cursor, f"{CURATED}.DIM_MAGNITUDE_TYPE"),
        "event_statuses": _count(cursor, f"{CURATED}.DIM_EVENT_STATUS"),
        "current_events": _count(cursor, f"{CURATED}.EVENT_CURRENT"),
    }


def _audit(cursor, status: str, attempt_id: str = ATTEMPT_ID) -> int:
    return _count(
        cursor,
        f"{CURATED}.BATCH_PROCESS_ATTEMPT",
        "WHERE ATTEMPT_ID = %s AND STATUS = %s",
        (attempt_id, status),
    )


def _duplicates(cursor) -> dict[str, int]:
    result = {}
    for table, columns in (
        ("FACT_EVENT_REVISION", "CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH"),
        ("BRIDGE_EVENT_SITE", "CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY"),
    ):
        cursor.execute(
            f"SELECT COUNT(*) FROM (SELECT {columns} FROM {CURATED}.{table} "
            f"GROUP BY {columns} HAVING COUNT(*) > 1)"
        )
        result[table] = int(cursor.fetchone()[0])
    return result


def execute() -> dict:
    """Run only after explicit warehouse-cost and conditional-delete approval."""
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            cursor.execute(
                f"SHOW USER PROCEDURES LIKE 'PROCESS_LOADED_ATTEMPT_FAILURE_DEMO' "
                f"IN SCHEMA {CURATED}"
            )
            if cursor.fetchall():
                raise RuntimeError("failure demo procedure already exists; inspect before retry")
            before = _snapshot(cursor)
            if before["raw"] != 1 or before["receipts"] != 1:
                raise RuntimeError(f"fixture RAW is not the expected one-row load: {before}")
            if any(_duplicates(cursor).values()):
                raise RuntimeError("fixture has duplicate logical keys before drill")
            failed_before = _audit(cursor, "failed")
            complete_before = _audit(cursor, "complete")
            if complete_before < 1:
                raise RuntimeError("fixture original has not completed its initial processing")

            cursor.execute(CREATE_SQL)
            cursor.execute(f"CALL {DEMO_PROCEDURE}(%s)", (ATTEMPT_ID,))
            failed_result = json.loads(cursor.fetchone()[0])
            if failed_result != {"status": "failed_as_planned", "attempt_id": ATTEMPT_ID}:
                raise RuntimeError(f"unexpected failure demo result: {failed_result}")
            after_failure = _snapshot(cursor)
            if after_failure != before or _audit(cursor, "failed") != failed_before + 1:
                raise RuntimeError(
                    "failed transform did not preserve models and append failure audit"
                )

            cursor.execute(f"CALL {CURATED}.PROCESS_LOADED_ATTEMPT(%s)", (ATTEMPT_ID,))
            retry = json.loads(cursor.fetchone()[0])
            after_retry = _snapshot(cursor)
            if (
                retry.get("status") != "complete"
                or retry.get("revision_rows_merged") != 0
                or after_retry != before
                or _audit(cursor, "complete") != complete_before + 1
                or any(_duplicates(cursor).values())
            ):
                raise RuntimeError("retry did not converge without duplicate logical keys")
            return {
                "status": "pass",
                "before": before,
                "after_failure": after_failure,
                "after_retry": after_retry,
                "failure_audits_added": 1,
                "retry_process_id": retry["process_attempt_id"],
                "revision_duplicate_groups": 0,
                "bridge_duplicate_groups": 0,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run paid Snowflake recovery drill")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        print("Recovery drill preview only; no Snowflake connection")
        print(f"Database: {TEST_DATABASE}; loaded attempt: {ATTEMPT_ID}")
        print(
            "Plan: guard RAW/model state; create isolated failure procedure; "
            "fail after writes; verify rollback/audit; retry from RAW; check keys"
        )
        print("Live execution needs separate warehouse-cost and conditional-delete approval")


if __name__ == "__main__":
    main()
