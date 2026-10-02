"""Preview or load two old-origin synthetic attempts into isolated fixture RAW."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import _result_dicts, connect_project, reconcile_loaded_rows
from scripts.evidence.phase2.fixture_original import CURATED
from scripts.evidence.phase2.fixture_raw_load import (
    RAW_TABLE,
    RECEIPT_TABLE,
    _append_receipt,
    local_plans,
)
from scripts.evidence.phase2.fixture_stale_replay import (
    ATTEMPT_ID as REPLAY_ATTEMPT,
)
from scripts.evidence.phase2.fixture_stale_replay import (
    EXPECTED_AFTER as REPLAY_COUNTS,
)
from scripts.evidence.phase2.fixture_stale_replay import (
    _counts,
)
from scripts.fixtures.build_phase2_fixture_attempts import SEQUENCE as PRIOR_SEQUENCE
from scripts.fixtures.build_phase2_old_origin_attempts import SEQUENCE

REPLAY_PROCESS_ID = "516de8b981d7486d85b27ccf1d974fb0"


def _guard_before(cursor, plans: list[dict]) -> None:
    expected_prior = sorted((attempt_id, 1) for attempt_id, _ in PRIOR_SEQUENCE)
    for table in (RAW_TABLE, RECEIPT_TABLE):
        cursor.execute(f"SELECT ATTEMPT_ID, COUNT(*) FROM {table} GROUP BY ATTEMPT_ID ORDER BY ATTEMPT_ID")
        if cursor.fetchall() != expected_prior:
            raise RuntimeError(f"fixture RAW baseline differs: {table}")
    if _counts(cursor) != REPLAY_COUNTS:
        raise RuntimeError("fixture curated model is not at measured stale-replay state")
    cursor.execute(f"SELECT COUNT(*) FROM {CURATED}.EVENT_CURRENT")
    if cursor.fetchone()[0] != 0:
        raise RuntimeError("fixture deleted event unexpectedly current")
    cursor.execute(f"""
        SELECT PROCESS_ATTEMPT_ID, STATUS FROM {CURATED}.BATCH_PROCESS_ATTEMPT
        WHERE ATTEMPT_ID = %s
    """, (REPLAY_ATTEMPT,))
    if cursor.fetchall() != [(REPLAY_PROCESS_ID, "complete")]:
        raise RuntimeError("fixture stale-replay audit differs")
    for plan in plans:
        cursor.execute(f"LIST {plan['stage_path']}")
        if cursor.fetchall():
            raise RuntimeError(f"fixture stage path already contains files: {plan['attempt_id']}")


def _guard_after(cursor, plans: list[dict]) -> None:
    expected_all = sorted((attempt_id, 1) for attempt_id, _ in PRIOR_SEQUENCE + SEQUENCE)
    for table in (RAW_TABLE, RECEIPT_TABLE):
        cursor.execute(f"SELECT ATTEMPT_ID, COUNT(*) FROM {table} GROUP BY ATTEMPT_ID ORDER BY ATTEMPT_ID")
        if cursor.fetchall() != expected_all:
            raise RuntimeError(f"fixture RAW postload counts differ: {table}")
    for plan in plans:
        cursor.execute(f"""
            SELECT EXTRACT_STATUS, LOAD_STATUS, SOURCE_ROWS_RETURNED,
                   RAW_ROWS_WRITTEN, LOADED_ROWS,
                   COALESCE(ARRAY_SIZE(COVERAGE_GAPS), 0),
                   MANIFEST:fixture_only::BOOLEAN
            FROM {RECEIPT_TABLE} WHERE ATTEMPT_ID = %s
        """, (plan["attempt_id"],))
        if cursor.fetchall() != [("complete", "complete", 1, 1, 1, 0, True)]:
            raise RuntimeError(f"fixture RAW receipt differs: {plan['attempt_id']}")


def execute_load() -> list[dict]:
    """Load only two reviewed attempts after separate Snowflake-cost approval."""
    plans = local_plans(SEQUENCE)
    results = []
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            _guard_before(cursor, plans)
            for plan in plans:
                loaded = 0
                copy_results = []
                try:
                    cursor.execute(f"PUT '{plan['events_path'].as_uri()}' {plan['stage_path']} "
                                   "AUTO_COMPRESS=FALSE OVERWRITE=FALSE")
                    put = _result_dicts(cursor)
                    if len(put) != 1 or put[0].get("status", "").upper() != "UPLOADED":
                        raise RuntimeError("old-origin fixture PUT did not upload one new file")
                    cursor.execute(plan["copy_sql"])
                    copy_results = _result_dicts(cursor)
                    if len(copy_results) != 1 or copy_results[0].get("status", "").upper() != "LOADED":
                        raise RuntimeError("old-origin fixture COPY did not load one file")
                    loaded = int(copy_results[0]["rows_loaded"])
                    cursor.execute(f"SELECT COUNT(*) FROM {RAW_TABLE} WHERE ATTEMPT_ID = %s",
                                   (plan["attempt_id"],))
                    reconcile_loaded_rows(1, loaded, int(cursor.fetchone()[0]))
                except Exception as exc:
                    _append_receipt(cursor, plan, "failed", loaded, copy_results, exc)
                    raise
                _append_receipt(cursor, plan, "complete", loaded, copy_results)
                results.append({"attempt_id": plan["attempt_id"], "loaded_rows": loaded})
            _guard_after(cursor, plans)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run two paid fixture RAW loads")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_load(), indent=2))
    else:
        plans = local_plans(SEQUENCE)
        print("Phase 2 old-origin RAW load: preview only; no Snowflake connection")
        print(f"Attempts: {', '.join(p['attempt_id'] for p in plans)}")
        print("Guard: exact four-attempt fixture state and empty new stage paths")
        print("Then: two one-row PUT/COPY loads, count reconciliation, and synthetic receipts")


if __name__ == "__main__":
    main()
