"""Plan fixed origin-time windows for the public five-year history load."""

import argparse
import calendar
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quakewatch.extract_batch import iso_utc, parse_utc, run_batch
from quakewatch.logs import configure_logging
from quakewatch.settings import EVENT_HORIZON_YEARS, MAX_HISTORY_BATCH_WINDOWS, SITES


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


def captured_history_windows(cutoff: datetime, output: Path) -> dict[int, Path]:
    """Find complete local captures; these are not proof of Snowflake loading."""
    expected = {
        (site, iso_utc(start), iso_utc(end)): number
        for number, (site, start, end) in enumerate(history_windows(cutoff), start=1)
    }
    captured: dict[int, Path] = {}
    for path in sorted(output.glob("*/manifest.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("status") != "complete" or manifest.get("coverage_gaps"):
                continue
            site_name = manifest["site"]["name"]
            site = next(key for key, config in SITES.items() if config.name == site_name)
            key = (site, iso_utc(parse_utc(manifest["requested_starttime"])),
                   iso_utc(parse_utc(manifest["requested_endtime"])))
            number = expected.get(key)
            if number and (path.parent / manifest["events_file"]).is_file():
                captured[number] = path
        except (KeyError, ValueError, TypeError, StopIteration):
            continue
    return captured


def resume_capture(cutoff: datetime, output: Path, max_windows: int, execute: bool,
                   start_window: int = 1, source_days: int | None = None,
                   resume_children: bool = False,
                   source_hours: int | None = None,
                   hourly_child: int | None = None) -> list[int]:
    """Process a bounded consecutive run, stopping at the first source gap."""
    if not 1 <= max_windows <= MAX_HISTORY_BATCH_WINDOWS:
        raise ValueError(f"max-windows must be between 1 and {MAX_HISTORY_BATCH_WINDOWS}")
    windows = history_windows(cutoff)
    if not 1 <= start_window <= len(windows):
        raise ValueError(f"start-window must be between 1 and {len(windows)}")
    if source_days is not None and not 1 <= source_days <= 7:
        raise ValueError("source-days must be between 1 and 7")
    if source_hours is not None and (source_days != 1 or not 1 <= source_hours <= 12):
        raise ValueError("source-hours requires source-days 1 and must be between 1 and 12")
    if hourly_child is not None and (source_hours is None or hourly_child < 1):
        raise ValueError("hourly-child requires source-hours and a positive child number")
    captured = captured_history_windows(cutoff, output)
    pending = [number for number in range(start_window, len(windows) + 1)
               if number not in captured]
    selected = pending[:max_windows]
    for number in selected:
        site, start, end = windows[number - 1]
        print(number, site, iso_utc(start), iso_utc(end))
        if not execute:
            continue
        if source_days is None:
            manifest_path = run_batch(site, start, end, output)
        else:
            options: dict[str, Any] = {"source_days": source_days}
            if resume_children:
                options["resume_children"] = True
            if source_hours is not None:
                options["source_hours"] = source_hours
            if hourly_child is not None:
                options["hourly_child"] = hourly_child
            manifest_path = run_batch(site, start, end, output, **options)
        print(f"Captured manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "complete" or manifest.get("coverage_gaps"):
            raise RuntimeError(f"Window {number} did not reconcile; inspect {manifest_path}")
    if not execute:
        print(f"Preview only: {len(selected)} windows; no USGS or Snowflake calls made.")
    else:
        print(f"Captured {len(selected)} windows locally; no Snowflake calls made.")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or extract one five-year history window")
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    parser.add_argument("--window", type=int, help="1-based window number; required to execute")
    parser.add_argument("--execute", action="store_true", help="Fetch only the selected window from USGS")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--resume-preview", action="store_true", help="Show next uncaptured local window")
    parser.add_argument("--resume", action="store_true", help="Process consecutive uncaptured windows")
    parser.add_argument("--max-windows", type=int, help="Resume limit, 1 to 50")
    parser.add_argument("--start-window", type=int, default=1,
                        help="Explicit first eligible window; earlier gaps remain unresolved")
    parser.add_argument("--source-days", type=int,
                        help="Start with audited source slices of 1 to 7 days")
    parser.add_argument("--source-hours", type=int,
                        help="Split uncached daily children into audited 1 to 12 hour slices")
    parser.add_argument("--hourly-child", type=int,
                        help="Apply source-hours only to this 1-based daily child")
    parser.add_argument("--resume-children", action="store_true",
                        help="Reuse validated local child checkpoints from prior attempts")
    args = parser.parse_args()
    configure_logging()
    if args.resume_children and args.source_days is None:
        parser.error("--resume-children requires --source-days")
    if args.source_hours is not None and (args.source_days != 1
                                          or not 1 <= args.source_hours <= 12):
        parser.error("--source-hours requires --source-days 1 and a value from 1 to 12")
    if args.hourly_child is not None and (args.source_hours is None
                                          or args.hourly_child < 1):
        parser.error("--hourly-child requires --source-hours and a positive child number")
    windows = history_windows(args.cutoff)
    if args.resume:
        if args.window is not None or args.resume_preview or args.max_windows is None:
            parser.error("--resume requires --max-windows and cannot use --window or --resume-preview")
        try:
            resume_capture(args.cutoff, args.output, args.max_windows, args.execute,
                           args.start_window, args.source_days, args.resume_children,
                           args.source_hours, args.hourly_child)
        except ValueError as exc:
            parser.error(str(exc))
        return
    if args.max_windows is not None:
        parser.error("--max-windows requires --resume")
    if args.start_window != 1:
        parser.error("--start-window requires --resume")
    if args.source_days is not None and not 1 <= args.source_days <= 7:
        parser.error("source-days must be between 1 and 7")
    if args.resume_preview:
        if args.window is not None or args.execute:
            parser.error("--resume-preview cannot be combined with --window or --execute")
        captured = captured_history_windows(args.cutoff, args.output)
        next_number = next((number for number in range(1, len(windows) + 1)
                            if number not in captured), None)
        print(f"Locally captured windows: {len(captured)} of {len(windows)}")
        if next_number is None:
            print("All windows captured locally; Snowflake load status not checked.")
        else:
            site, start, end = windows[next_number - 1]
            print("Next uncaptured:", next_number, site, iso_utc(start), iso_utc(end))
        print("Preview only; no USGS or Snowflake calls made.")
        return
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
    if args.source_days is None:
        manifest_path = run_batch(site_key, start, end, args.output)
    else:
        options: dict[str, Any] = {"source_days": args.source_days}
        if args.resume_children:
            options["resume_children"] = True
        if args.source_hours is not None:
            options["source_hours"] = args.source_hours
        if args.hourly_child is not None:
            options["hourly_child"] = args.hourly_child
        manifest_path = run_batch(site_key, start, end, args.output, **options)
    print(f"Captured manifest: {manifest_path}")


if __name__ == "__main__":
    main()
