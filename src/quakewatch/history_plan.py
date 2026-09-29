"""Plan fixed origin-time windows for the public five-year history load."""

import argparse
import calendar
from datetime import UTC, datetime

from quakewatch.extract_batch import iso_utc, parse_utc
from quakewatch.settings import EVENT_HORIZON_YEARS, SITES


def years_before(value: datetime, years: int) -> datetime:
    """Keep month/day where possible; clamp February 29 in non-leap years."""
    year = value.year - years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def history_windows(cutoff: datetime) -> list[tuple[str, datetime, datetime]]:
    """Produce contiguous, fixed yearly origin-time requests for each site."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("history cutoff must have a timezone")
    cutoff = cutoff.astimezone(UTC)
    boundaries = [
        years_before(cutoff, remaining)
        for remaining in range(EVENT_HORIZON_YEARS, -1, -1)
    ]
    return [
        (site_key, boundaries[index], boundaries[index + 1])
        for site_key in SITES
        for index in range(EVENT_HORIZON_YEARS)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Print five-year origin-time windows; no requests run")
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    args = parser.parse_args()
    windows = history_windows(args.cutoff)
    for site_key, start, end in windows:
        print(site_key, iso_utc(start), iso_utc(end))
    print(f"Planned windows: {len(windows)}; no USGS or Snowflake calls made.")


if __name__ == "__main__":
    main()
