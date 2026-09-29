"""Inventory locally captured history attempts for a future Snowflake RAW load."""

import argparse
from pathlib import Path

from quakewatch.extract_batch import parse_utc
from quakewatch.history_plan import captured_history_windows
from quakewatch.raw_load import plan_raw_load


def load_candidates(cutoff, output: Path) -> list[tuple[int, dict]]:
    """Validate one local capture per history window without checking Snowflake."""
    candidates = []
    for number, path in sorted(captured_history_windows(cutoff, output).items()):
        candidates.append((number, plan_raw_load(path)))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview local RAW load candidates only")
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    candidates = load_candidates(args.cutoff, args.output)
    for number, plan in candidates:
        print(f"Window {number}: {plan['attempt_id']} ({plan['expected_rows']} rows)")
    print(f"Validated local candidates: {len(candidates)}")
    print("Snowflake load status unknown; no account connection, PUT, or COPY performed.")


if __name__ == "__main__":
    main()
