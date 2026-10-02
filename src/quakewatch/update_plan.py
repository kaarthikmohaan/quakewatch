"""Preview a catalog-wide update sweep without network calls or state writes."""

import argparse
import json
from datetime import UTC, datetime, timedelta

from quakewatch.extract_batch import iso_utc, parse_utc
from quakewatch.logs import configure_logging


def plan_update_sweep(catalog_start: datetime, cutoff: datetime,
                      last_watermark: datetime, sweep_started_at: datetime,
                      overlap_seconds: int) -> dict:
    """Keep origin-time bounds separate from the source-update watermark."""
    dates = (catalog_start, cutoff, last_watermark, sweep_started_at)
    if any(value.tzinfo is None or value.utcoffset() is None for value in dates):
        raise ValueError("all sweep dates must have a timezone")
    catalog_start, cutoff, last_watermark, sweep_started_at = (
        value.astimezone(UTC) for value in dates
    )
    if not catalog_start < cutoff <= sweep_started_at:
        raise ValueError("require catalog-start < cutoff <= sweep-started-at")
    if last_watermark > sweep_started_at:
        raise ValueError("last-watermark cannot be later than sweep-started-at")
    if isinstance(overlap_seconds, bool) or not isinstance(overlap_seconds, int) or overlap_seconds <= 0:
        raise ValueError("overlap-seconds must be a positive integer")
    try:
        updated_after = last_watermark - timedelta(seconds=overlap_seconds)
    except OverflowError as exc:
        raise ValueError("overlap exceeds the supported datetime range") from exc
    return {
        "status": "preview",
        "catalog_lower_bound": iso_utc(catalog_start),
        "origin_time_cutoff": iso_utc(cutoff),
        "sweep_started_at": iso_utc(sweep_started_at),
        "last_committed_watermark": iso_utc(last_watermark),
        "overlap_seconds": overlap_seconds,
        "proposed_watermark_after_success": iso_utc(sweep_started_at),
        "watermark_advanced": False,
        "query_parameters": {
            "format": "geojson",
            "starttime": iso_utc(catalog_start),
            "endtime": iso_utc(cutoff),
            "updatedafter": iso_utc(updated_after),
            "includedeleted": "true",
            "orderby": "time-asc",
        },
        "count_sizing_pending": True,
        "note": "Preview only; no source requests, Snowflake calls, or watermark writes. "
                "Execution must count-size and reconcile every window and RAW load before committing "
                "the proposed watermark. Source results are not a consistent catalog snapshot.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-start", type=parse_utc, required=True)
    parser.add_argument("--cutoff", type=parse_utc, required=True)
    parser.add_argument("--last-watermark", type=parse_utc, required=True)
    parser.add_argument("--sweep-started-at", type=parse_utc, required=True)
    parser.add_argument("--overlap-seconds", type=int, required=True)
    args = parser.parse_args()
    configure_logging()
    try:
        plan = plan_update_sweep(args.catalog_start, args.cutoff, args.last_watermark,
                                 args.sweep_started_at, args.overlap_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
