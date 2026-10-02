"""Inventory locally captured history attempts eligible for a Snowflake RAW load."""

import argparse
from contextlib import closing
from pathlib import Path

from quakewatch.extract_batch import parse_utc
from quakewatch.history_plan import captured_history_windows
from quakewatch.logs import configure_logging
from quakewatch.raw_load import connect_project, plan_raw_load


def load_candidates(cutoff, output: Path) -> list[tuple[int, dict]]:
    """Validate one local capture per history window without checking Snowflake."""
    candidates = []
    for number, path in sorted(captured_history_windows(cutoff, output).items()):
        candidates.append((number, plan_raw_load(path)))
    return candidates


def classify_loads(candidates: list[tuple[int, dict]], receipts: list[tuple],
                   raw_counts: list[tuple]) -> list[tuple[int, dict, str]]:
    """Require one matching complete receipt and RAW count before calling an attempt loaded."""
    by_attempt: dict[str, list[tuple]] = {}
    for attempt_id, status, loaded_rows in receipts:
        by_attempt.setdefault(attempt_id, []).append((status, loaded_rows))
    raw_by_attempt = dict(raw_counts)
    results = []
    for number, plan in candidates:
        attempt_id = plan["attempt_id"]
        matching = by_attempt.get(attempt_id, [])
        raw_rows = int(raw_by_attempt.get(attempt_id, 0))
        if not matching and raw_rows == 0:
            state = "ready"
        elif (len(matching) == 1 and matching[0][0] == "complete"
              and matching[0][1] is not None
              and int(matching[0][1]) == raw_rows == plan["expected_rows"]):
            state = "loaded"
        else:
            state = "investigate"
        results.append((number, plan, state))
    return results


def check_snowflake(candidates: list[tuple[int, dict]], connection) -> list[tuple[int, dict, str]]:
    """Read existing receipt and RAW counts; never upload or modify warehouse data."""
    if not candidates:
        return []
    ids = [plan["attempt_id"] for _, plan in candidates]
    placeholders = ", ".join(["%s"] * len(ids))
    with closing(connection.cursor()) as cursor:
        cursor.execute(
            f"SELECT ATTEMPT_ID, LOAD_STATUS, LOADED_ROWS FROM QUAKEWATCH.RAW.BATCH_ATTEMPT "
            f"WHERE ATTEMPT_ID IN ({placeholders})", tuple(ids)
        )
        receipts = cursor.fetchall()
        cursor.execute(
            f"SELECT ATTEMPT_ID, COUNT(*) FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS "
            f"WHERE ATTEMPT_ID IN ({placeholders}) GROUP BY ATTEMPT_ID", tuple(ids)
        )
        raw_counts = cursor.fetchall()
    return classify_loads(candidates, receipts, raw_counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview local RAW load candidates only")
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--check-snowflake", action="store_true",
                        help="Read warehouse receipts and RAW counts (may incur cost)")
    args = parser.parse_args()
    configure_logging()
    candidates = load_candidates(args.cutoff, args.output)
    if args.check_snowflake and candidates:
        with closing(connect_project()) as connection:
            statuses = check_snowflake(candidates, connection)
        for number, plan, state in statuses:
            print(f"Window {number}: {plan['attempt_id']} ({plan['expected_rows']} rows) {state}")
        print("Counts:", ", ".join(f"{state}={sum(row[2] == state for row in statuses)}"
                                    for state in ("loaded", "ready", "investigate")))
        print("Read-only Snowflake check; no PUT or COPY performed.")
    else:
        for number, plan in candidates:
            print(f"Window {number}: {plan['attempt_id']} ({plan['expected_rows']} rows)")
        print(f"Validated local candidates: {len(candidates)}")
        print("Snowflake load status unknown; no account connection, PUT, or COPY performed.")


if __name__ == "__main__":
    main()
