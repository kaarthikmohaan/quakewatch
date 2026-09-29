"""Plan fixed origin-time windows for the public five-year history load."""

import argparse
import calendar
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.extract_batch import iso_utc, parse_utc, run_batch
from quakewatch.settings import EVENT_HORIZON_YEARS, SITES


def months_before(value: datetime, months: int) -> datetime:
    """Keep the cutoff's day where possible; clamp short months."""
    year, month_index = divmod(value.year * 12 + value.month - 1 - months, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def history_windows(cutoff: datetime) -> list[tuple[str, datetime, datetime]]:
    """Produce contiguous, fixed monthly origin-time requests for each site."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("history cutoff must have a timezone")
    cutoff = cutoff.astimezone(UTC)
    month_count = EVENT_HORIZON_YEARS * 12
    boundaries = [months_before(cutoff, remaining) for remaining in range(month_count, -1, -1)]
    return [
        (site_key, boundaries[index], boundaries[index + 1])
        for site_key in SITES
        for index in range(month_count)
    ]


def selected_history_window(cutoff: datetime, number: int) -> tuple[str, datetime, datetime]:
    """Select one 1-based window; never start the whole plan by accident."""
    windows = history_windows(cutoff)
    if number < 1 or number > len(windows):
        raise ValueError(f"window must be between 1 and {len(windows)}")
    return windows[number - 1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or extract one five-year history window")
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    parser.add_argument("--window", type=int, help="1-based window number; required to execute")
    parser.add_argument("--execute", action="store_true", help="Fetch only the selected window from USGS")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    windows = history_windows(args.cutoff)
    if args.window is None:
        if args.execute:
            parser.error("--execute requires --window so only one request runs")
        for number, (site_key, start, end) in enumerate(windows, start=1):
            print(number, site_key, iso_utc(start), iso_utc(end))
        print(f"Planned windows: {len(windows)}; no USGS or Snowflake calls made.")
        return
    try:
        site_key, start, end = selected_history_window(args.cutoff, args.window)
    except ValueError as exc:
        parser.error(str(exc))
    print(args.window, site_key, iso_utc(start), iso_utc(end))
    if not args.execute:
        print("Preview only; add --execute to fetch this one window.")
        return
    manifest_path = run_batch(site_key, start, end, args.output)
    print(f"Captured manifest: {manifest_path}")


if __name__ == "__main__":
    main()
