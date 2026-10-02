"""Process the old-origin original and update in one guarded fixture session."""

from __future__ import annotations

import argparse
import json

from quakewatch.raw_load import connect_project
from scripts.evidence.phase2.phase2_fixture_original import CURATED
from scripts.evidence.phase2.phase2_old_origin_original import (
    ATTEMPT_ID as ORIGINAL_ATTEMPT, _guard_after as original_after,
    _guard_before as original_before,
)
from scripts.evidence.phase2.phase2_old_origin_update import (
    ATTEMPT_ID as UPDATE_ATTEMPT, _guard_after as update_after,
    _guard_before as update_before,
)


def execute_pair() -> dict:
    """Run two guarded calls after approval for cost and conditional deletes."""
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            original_hash = original_before(cursor)
            cursor.execute(f"CALL {CURATED}.PROCESS_LOADED_ATTEMPT(%s)", (ORIGINAL_ATTEMPT,))
            original_outcome = json.loads(cursor.fetchone()[0])
            original_counts = original_after(cursor, original_outcome, original_hash)
            original = {"outcome": original_outcome, "counts": original_counts}
            print(json.dumps({"original": original}, indent=2, sort_keys=True), flush=True)
            original_process_id = original_outcome["process_attempt_id"]
            update_hash = update_before(cursor, original_process_id)
            cursor.execute(f"CALL {CURATED}.PROCESS_LOADED_ATTEMPT(%s)", (UPDATE_ATTEMPT,))
            update_outcome = json.loads(cursor.fetchone()[0])
            update_counts = update_after(cursor, update_outcome, update_hash,
                                         original_process_id)
            return {"original": original, "update": {"outcome": update_outcome,
                                                       "counts": update_counts}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run two paid fixture procedure calls")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_pair(), indent=2, sort_keys=True))
    else:
        print("Phase 2 old-origin pair: preview only; no Snowflake connection")
        print(f"Order: {ORIGINAL_ATTEMPT}, then {UPDATE_ATTEMPT}")
        print("Each call requires exact pre-state and verifies revision, current view, audit, and keys")
        print("The update call runs only after the original post-check passes")


if __name__ == "__main__":
    main()
