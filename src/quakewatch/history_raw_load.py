"""Run a bounded, resumable RAW load for validated history captures."""

import argparse
from contextlib import closing
from pathlib import Path

from quakewatch.extract_batch import parse_utc
from quakewatch.history_load_plan import check_snowflake, load_candidates
from quakewatch.raw_load import connect_project, execute_raw_load
from quakewatch.settings import MAX_HISTORY_BATCH_WINDOWS


def load_ready(candidates: list[tuple[int, dict]], connection, max_windows: int) -> list[int]:
    """Load at most N ready attempts, rechecking each immediately before COPY."""
    if not 1 <= max_windows <= MAX_HISTORY_BATCH_WINDOWS:
        raise ValueError(f"max-windows must be between 1 and {MAX_HISTORY_BATCH_WINDOWS}")
    statuses = check_snowflake(candidates, connection)
    if any(state == "investigate" for _, _, state in statuses):
        raise RuntimeError("A candidate needs investigation; no RAW loads started")
    ready = [(number, plan) for number, plan, state in statuses if state == "ready"]
    completed = []
    for number, plan in ready[:max_windows]:
        current = check_snowflake([(number, plan)], connection)[0][2]
        if current != "ready":
            raise RuntimeError(f"Window {number} changed to {current}; stop before PUT/COPY")
        loaded = execute_raw_load(plan, connection)
        print(f"Window {number}: loaded and reconciled {loaded} RAW rows")
        completed.append(number)
    print(f"Loaded {len(completed)} windows; {len(ready) - len(completed)} ready windows remain.")
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or execute a bounded history RAW load")
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--max-windows", required=True, type=int, help="Maximum ready windows, 1 to 50")
    parser.add_argument("--execute", action="store_true", help="Connect to Snowflake and run PUT/COPY")
    args = parser.parse_args()
    if not 1 <= args.max_windows <= MAX_HISTORY_BATCH_WINDOWS:
        parser.error(f"max-windows must be between 1 and {MAX_HISTORY_BATCH_WINDOWS}")
    candidates = load_candidates(args.cutoff, args.output)
    print(f"Validated local candidates: {len(candidates)}")
    if not args.execute:
        print("Preview only. Snowflake status unknown; no account connection, PUT, or COPY.")
        print("Execution will check Snowflake and load at most", args.max_windows, "ready windows.")
        return
    with closing(connect_project()) as connection:
        load_ready(candidates, connection, args.max_windows)


if __name__ == "__main__":
    main()
