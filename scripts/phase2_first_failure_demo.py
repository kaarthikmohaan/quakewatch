"""First-ever transform failure and RAW-only retry for one new synthetic batch."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from quakewatch.raw_load import _result_dicts, connect_project, reconcile_loaded_rows
from scripts.build_phase2_fixture_attempts import build_attempts
from scripts.phase2_fixture_original import CURATED, RAW
from scripts.phase2_fixture_raw_load import _append_receipt, local_plans
from scripts.phase2_recovery_demo import DEMO_PROCEDURE, _audit, _duplicates, _snapshot


ATTEMPT_ID = "fixture-first-failure-v1"
FIXTURE = "normal_event.json"
SEQUENCE = ((ATTEMPT_ID, FIXTURE),)


def _plan() -> dict:
    build_attempts(sequence=SEQUENCE, fetch_base=datetime(2026, 10, 1, tzinfo=UTC))
    return local_plans(sequence=SEQUENCE)[0]


def _raw_hash(cursor) -> str:
    cursor.execute(f"SELECT PAYLOAD_HASH FROM {RAW}.RAW_EVENT_RECORDS "
                   "WHERE ATTEMPT_ID = %s", (ATTEMPT_ID,))
    rows = cursor.fetchall()
    if len(rows) != 1 or not rows[0][0]:
        raise RuntimeError("new fixture does not have exactly one RAW payload hash")
    return rows[0][0]


def _retry_counts_match(retry: dict, loaded_snapshot: dict[str, int],
                        after_retry: dict[str, int]) -> bool:
    """A MERGE update may count as merged without adding a logical fact row."""
    expected_after = {**loaded_snapshot,
                      "staging": loaded_snapshot["staging"] + 1,
                      "batches": loaded_snapshot["batches"] + 1}
    merged = retry.get("revision_rows_merged")
    return (retry.get("status") == "complete"
            and retry.get("loaded_rows") == 1
            and retry.get("processed_rows") == 1
            and retry.get("rejected_rows") == 0
            and isinstance(merged, int) and merged >= 0
            and after_retry == expected_after)


def execute() -> dict:
    """Run only after new approval for paid COPY, calls, and conditional deletes."""
    plan = _plan()
    expected_hash = json.loads(plan["events_path"].read_text())["metadata"]["payload_hash"]
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            cursor.execute(f"SHOW USER PROCEDURES LIKE 'PROCESS_LOADED_ATTEMPT_FAILURE_DEMO' "
                           f"IN SCHEMA {CURATED}")
            if len(cursor.fetchall()) != 1:
                raise RuntimeError("reviewed fixture failure procedure is missing or ambiguous")
            before = _snapshot(cursor, ATTEMPT_ID)
            if before["raw"] or before["receipts"] or _audit(cursor, "failed", ATTEMPT_ID) \
                    or _audit(cursor, "complete", ATTEMPT_ID):
                raise RuntimeError("new fixture attempt already exists; inspect before retry")
            cursor.execute(f"LIST {plan['stage_path']}")
            if cursor.fetchall():
                raise RuntimeError("new fixture stage path already has files")
            if any(_duplicates(cursor).values()):
                raise RuntimeError("fixture has duplicate logical keys before load")

            loaded = 0
            copy_results = []
            try:
                cursor.execute(f"PUT '{plan['events_path'].as_uri()}' {plan['stage_path']} "
                               "AUTO_COMPRESS=FALSE OVERWRITE=FALSE")
                put = _result_dicts(cursor)
                if len(put) != 1 or put[0].get("status", "").upper() != "UPLOADED":
                    raise RuntimeError("new fixture PUT did not upload one file")
                cursor.execute(plan["copy_sql"])
                copy_results = _result_dicts(cursor)
                if len(copy_results) != 1 or copy_results[0].get("status", "").upper() != "LOADED":
                    raise RuntimeError("new fixture COPY did not load one file")
                loaded = int(copy_results[0]["rows_loaded"])
                cursor.execute(f"SELECT COUNT(*) FROM {RAW}.RAW_EVENT_RECORDS "
                               "WHERE ATTEMPT_ID = %s", (ATTEMPT_ID,))
                reconcile_loaded_rows(1, loaded, int(cursor.fetchone()[0]))
                if _raw_hash(cursor) != expected_hash:
                    raise RuntimeError("new fixture RAW payload hash differs")
            except Exception as error:
                _append_receipt(cursor, plan, "failed", loaded, copy_results, error)
                raise
            _append_receipt(cursor, plan, "complete", loaded, copy_results)
            loaded_snapshot = _snapshot(cursor, ATTEMPT_ID)
            if (loaded_snapshot["raw"] != 1 or loaded_snapshot["receipts"] != 1
                    or _audit(cursor, "failed", ATTEMPT_ID)
                    or _audit(cursor, "complete", ATTEMPT_ID)):
                raise RuntimeError("new fixture load receipt or process state differs")

            cursor.execute(f"CALL {DEMO_PROCEDURE}(%s)", (ATTEMPT_ID,))
            failure = json.loads(cursor.fetchone()[0])
            if failure != {"status": "failed_as_planned", "attempt_id": ATTEMPT_ID}:
                raise RuntimeError(f"unexpected failure response: {failure}")
            after_failure = _snapshot(cursor, ATTEMPT_ID)
            if (after_failure != loaded_snapshot or _raw_hash(cursor) != expected_hash
                    or _audit(cursor, "failed", ATTEMPT_ID) != 1
                    or _audit(cursor, "complete", ATTEMPT_ID)):
                raise RuntimeError("first transform failure did not preserve RAW/models")

            cursor.execute(f"CALL {CURATED}.PROCESS_LOADED_ATTEMPT(%s)", (ATTEMPT_ID,))
            retry = json.loads(cursor.fetchone()[0])
            after_retry = _snapshot(cursor, ATTEMPT_ID)
            if (not _retry_counts_match(retry, loaded_snapshot, after_retry)
                    or _raw_hash(cursor) != expected_hash
                    or _audit(cursor, "failed", ATTEMPT_ID) != 1
                    or _audit(cursor, "complete", ATTEMPT_ID) != 1
                    or any(_duplicates(cursor).values())):
                raise RuntimeError("first-failure retry did not converge")
            return {"status": "pass", "attempt_id": ATTEMPT_ID,
                    "loaded": loaded_snapshot, "after_failure": after_failure,
                    "after_retry": after_retry,
                    "failed_audits": 1, "complete_audits": 1,
                    "retry_process_id": retry["process_attempt_id"],
                    "revision_duplicate_groups": 0, "bridge_duplicate_groups": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run paid fixture drill")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True))
    else:
        plan = _plan()
        print("First-failure fixture preview only; no Snowflake connection")
        print(f"Attempt: {ATTEMPT_ID}; source: {FIXTURE}")
        print(f"Local manifest: {plan['events_path'].parent / 'manifest.json'}")
        print("Live order: guard absence; PUT/COPY/receipt; fail first transform; "
              "verify rollback; retry from unchanged RAW; check duplicate keys")


if __name__ == "__main__":
    main()
