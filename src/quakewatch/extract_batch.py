"""Download one bounded USGS earthquake query and preserve its source rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from quakewatch.settings import (
    MAX_RESULTS_PER_WINDOW,
    MAX_TARGET_RESULTS_PER_WINDOW,
    PARSER_VERSION,
    REQUEST_TIMEOUT_SECONDS,
    SOURCE_WINDOW_DEADLINE_SECONDS,
    SITES,
    USER_AGENT,
    USGS_COUNT_URL,
    USGS_QUERY_URL,
    Site,
)

MAX_HTTP_ATTEMPTS = 4
MAX_CONSECUTIVE_READ_TIMEOUTS = 2
MAX_WINDOW_RECONCILIATION_ATTEMPTS = 3
MAX_TIMEOUT_SPLIT_DEPTH = 3


class ExtractionError(RuntimeError):
    """Raised when a requested source window cannot be safely captured."""

    def __init__(self, message: str, window_audit: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.window_audit = window_audit or []


class SourceDeadlineExceeded(TimeoutError):
    """The bounded source capture exceeded its wall-clock budget."""


_source_deadline_at: ContextVar[float | None] = ContextVar("source_deadline_at", default=None)


def remaining_source_time() -> float | None:
    deadline_at = _source_deadline_at.get()
    if deadline_at is None:
        return None
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        raise SourceDeadlineExceeded("source window exceeded its wall-clock deadline")
    return remaining


@contextmanager
def source_deadline(seconds: int):
    """Share one wall-clock budget across retries and recursively split requests."""
    token = _source_deadline_at.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _source_deadline_at.reset(token)


def parse_utc(value: str) -> datetime:
    """Parse an ISO date/time. A date without a timezone is treated as UTC."""
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO date/time: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def request_with_retry(
    client: httpx.Client, url: str, params: dict[str, Any]
) -> httpx.Response:
    """Retry temporary HTTP/network failures a small, bounded number of times."""
    retryable_statuses = {429, 500, 502, 503, 504}
    consecutive_read_timeouts = 0
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        remaining = remaining_source_time()
        try:
            response = client.get(
                url, params=params,
                timeout=min(REQUEST_TIMEOUT_SECONDS, remaining)
                if remaining is not None else REQUEST_TIMEOUT_SECONDS,
            )
            remaining_source_time()
        except httpx.TransportError as exc:
            remaining_source_time()
            consecutive_read_timeouts = (
                consecutive_read_timeouts + 1 if isinstance(exc, httpx.ReadTimeout) else 0
            )
            if (attempt == MAX_HTTP_ATTEMPTS
                    or consecutive_read_timeouts >= MAX_CONSECUTIVE_READ_TIMEOUTS):
                raise
            delay = min(2 ** (attempt - 1), 8) + random.random() * 0.25
            remaining = remaining_source_time()
            time.sleep(min(delay, remaining) if remaining is not None else delay)
            continue

        consecutive_read_timeouts = 0
        if response.status_code not in retryable_statuses:
            return response
        if attempt == MAX_HTTP_ATTEMPTS:
            return response

        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = min(float(retry_after), 30.0) if retry_after else min(2 ** (attempt - 1), 8)
        except ValueError:
            delay = min(2 ** (attempt - 1), 8)
        delay += random.random() * 0.25
        remaining = remaining_source_time()
        time.sleep(min(delay, remaining) if remaining is not None else delay)

    raise AssertionError("retry loop ended unexpectedly")


def source_params(site: Site, start: datetime, end: datetime) -> dict[str, Any]:
    return {
        "format": "geojson",
        "starttime": iso_utc(start),
        "endtime": iso_utc(end),
        "latitude": site.latitude,
        "longitude": site.longitude,
        "maxradiuskm": site.radius_km,
        "includedeleted": "true",
        "orderby": "time-asc",
    }


def get_count(client: httpx.Client, params: dict[str, Any]) -> int:
    response = request_with_retry(client, USGS_COUNT_URL, params)
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        try:
            return int(response.text.strip())
        except ValueError:
            raise ExtractionError(
                f"USGS count endpoint returned an unrecognized response: {response.text!r}"
            ) from exc
    if isinstance(body, dict) and isinstance(body.get("count"), int):
        return body["count"]
    raise ExtractionError(f"USGS count endpoint returned an unrecognized JSON response: {body!r}")


def get_features(client: httpx.Client, params: dict[str, Any]) -> list[dict[str, Any]]:
    query_params = {**params, "limit": MAX_TARGET_RESULTS_PER_WINDOW}
    response = request_with_retry(client, USGS_QUERY_URL, query_params)
    if response.status_code == 204:
        return []
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise ExtractionError("USGS query returned malformed JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("features"), list):
        raise ExtractionError("USGS response is not a GeoJSON FeatureCollection")
    if any(not isinstance(feature, dict) for feature in body["features"]):
        raise ExtractionError("USGS FeatureCollection contains a malformed feature")
    return body["features"]


def split_window(start: datetime, end: datetime) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime]]:
    """Split an inclusive time range at its midpoint, intentionally overlapping there."""
    midpoint = start + (end - start) / 2
    if midpoint <= start or midpoint >= end:
        raise ExtractionError(
            f"Cannot split unresolved time window {iso_utc(start)} through {iso_utc(end)}"
        )
    # Both halves include the midpoint. The overlap avoids a boundary gap;
    # each returned row keeps its window ID so downstream processing can dedupe.
    return (start, midpoint), (midpoint, end)


def fetch_window(
    client: httpx.Client,
    site: Site,
    start: datetime,
    end: datetime,
    window_id: str,
    timeout_split_depth: int = 0,
) -> tuple[list[tuple[dict[str, Any], str]], list[dict[str, Any]]]:
    """Fetch one window; split oversized, mismatched, or timed-out requests."""
    params = source_params(site, start, end)
    last_issue = "source count changed during fetch"

    def unresolved(reason: str) -> dict[str, Any]:
        return {
            "window_id": window_id,
            "starttime": iso_utc(start),
            "endtime": iso_utc(end),
            "status": "unresolved",
            "reason": reason,
        }

    for attempt in range(1, MAX_WINDOW_RECONCILIATION_ATTEMPTS + 1):
        try:
            count_before = get_count(client, params)
        except httpx.ReadTimeout as exc:
            last_issue = f"source count timed out: {exc}"
            if timeout_split_depth >= MAX_TIMEOUT_SPLIT_DEPTH:
                raise ExtractionError(f"{window_id}: {last_issue}", [unresolved(last_issue)]) from exc
            break
        except (httpx.HTTPError, ExtractionError) as exc:
            raise ExtractionError(f"{window_id}: {exc}", [unresolved(str(exc))]) from exc
        if count_before >= MAX_TARGET_RESULTS_PER_WINDOW:
            last_issue = (
                f"count {count_before} reached safe target {MAX_TARGET_RESULTS_PER_WINDOW} "
                f"below service limit {MAX_RESULTS_PER_WINDOW}"
            )
            break

        try:
            features = get_features(client, params)
            count_after = get_count(client, params)
        except httpx.ReadTimeout as exc:
            last_issue = f"source fetch/count timed out: {exc}"
            if timeout_split_depth >= MAX_TIMEOUT_SPLIT_DEPTH:
                raise ExtractionError(f"{window_id}: {last_issue}", [unresolved(last_issue)]) from exc
            break
        except (httpx.HTTPError, ExtractionError) as exc:
            raise ExtractionError(f"{window_id}: {exc}", [unresolved(str(exc))]) from exc
        if len(features) == count_before == count_after:
            audit = {
                "window_id": window_id,
                "starttime": iso_utc(start),
                "endtime": iso_utc(end),
                "attempts": attempt,
                "count_before": count_before,
                "returned_rows": len(features),
                "count_after": count_after,
                "status": "reconciled",
            }
            return [(feature, window_id) for feature in features], [audit]
        last_issue = (
            f"counts disagree (before={count_before}, rows={len(features)}, after={count_after})"
        )

    try:
        left, right = split_window(start, end)
    except ExtractionError as exc:
        reason = f"{last_issue}; {exc}"
        raise ExtractionError(f"{window_id}: {reason}", [unresolved(reason)]) from exc

    rows: list[tuple[dict[str, Any], str]] = []
    audits: list[dict[str, Any]] = [
        {
            "window_id": window_id,
            "starttime": iso_utc(start),
            "endtime": iso_utc(end),
            "status": "split",
            "reason": last_issue,
        }
    ]
    for suffix, (child_start, child_end) in zip(("a", "b"), (left, right), strict=True):
        try:
            child_rows, child_audits = fetch_window(
                client, site, child_start, child_end, f"{window_id}.{suffix}",
                timeout_split_depth + 1,
            )
        except ExtractionError as exc:
            exc.window_audit = [*audits, *exc.window_audit]
            raise
        rows.extend(child_rows)
        audits.extend(child_audits)
    return rows, audits


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def initial_request_windows(start: datetime, end: datetime,
                            source_days: int | None) -> list[tuple[datetime, datetime]]:
    """Keep one logical month while optionally starting with shorter source calls."""
    if source_days is None:
        return [(start, end)]
    if not 1 <= source_days <= 7:
        raise ValueError("source-days must be between 1 and 7")
    windows = []
    cursor = start
    while cursor < end:
        next_end = min(cursor + timedelta(days=source_days), end)
        windows.append((cursor, next_end))
        cursor = next_end
    return windows


def run_batch(site_key: str, start: datetime, end: datetime, output_root: Path,
              source_days: int | None = None) -> Path:
    if start >= end:
        raise ExtractionError("--start must be earlier than --end")
    initial_windows = initial_request_windows(start, end, source_days)
    site = SITES[site_key]
    query_fingerprint = stable_json(
        {"site": asdict(site), "starttime": iso_utc(start), "endtime": iso_utc(end)}
    )
    logical_batch_id = hashlib.sha256(query_fingerprint.encode("utf-8")).hexdigest()[:20]
    attempt_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:10]}"
    fetched_at = iso_utc(datetime.now(UTC))
    attempt_dir = output_root / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    events_path = attempt_dir / "events.jsonl"
    manifest_path = attempt_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "logical_batch_id": logical_batch_id,
        "attempt_id": attempt_id,
        "site": asdict(site),
        "requested_starttime": iso_utc(start),
        "requested_endtime": iso_utc(end),
        "query_parameters": source_params(site, start, end),
        "initial_source_days": source_days,
        "fetched_at": fetched_at,
        "window_audit": [],
        "coverage_gaps": [],
        "source_rows_returned": 0,
        "raw_rows_written": 0,
        "events_file": events_path.name,
        "status": "running",
    }

    def save_manifest() -> None:
        temporary_path = manifest_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(manifest_path)

    save_manifest()
    windows: list[dict[str, Any]] = []
    active_window: tuple[str, datetime, datetime] | None = None
    try:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"}
        features: list[tuple[dict[str, Any], str]] = []
        if len(initial_windows) > 1:
            windows.append({
                "window_id": "w0001", "starttime": iso_utc(start),
                "endtime": iso_utc(end), "status": "split",
                "reason": f"planned source slices of at most {source_days} days",
            })
        with source_deadline(SOURCE_WINDOW_DEADLINE_SECONDS):
            with httpx.Client(
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                for index, (child_start, child_end) in enumerate(initial_windows, start=1):
                    window_id = f"w0001.{index}" if len(initial_windows) > 1 else "w0001"
                    active_window = (window_id, child_start, child_end)
                    manifest["active_window"] = {
                        "window_id": window_id, "starttime": iso_utc(child_start),
                        "endtime": iso_utc(child_end),
                    }
                    manifest["window_audit"] = windows
                    save_manifest()
                    try:
                        child_features, child_audits = fetch_window(
                            client, site, child_start, child_end, window_id
                        )
                    except ExtractionError as exc:
                        exc.window_audit = [*windows, *exc.window_audit]
                        raise
                    features.extend(child_features)
                    windows.extend(child_audits)
                    active_window = None
                    manifest.pop("active_window", None)
                    manifest["window_audit"] = windows
                    save_manifest()

        rows_written = 0
        with events_path.open("w", encoding="utf-8") as output:
            for feature, window_id in features:
                feature_json = stable_json(feature)
                record = {
                    "source_feature": feature,
                    "metadata": {
                        "logical_batch_id": logical_batch_id,
                        "attempt_id": attempt_id,
                        "window_id": window_id,
                        "fetched_at": fetched_at,
                        "payload_hash": hashlib.sha256(feature_json.encode("utf-8")).hexdigest(),
                        "parser_version": PARSER_VERSION,
                    },
                }
                output.write(stable_json(record) + "\n")
                rows_written += 1

        manifest.update(
            {
                "window_audit": windows,
                "source_rows_returned": len(features),
                "raw_rows_written": rows_written,
                "status": "complete",
            }
        )
        save_manifest()
    except (Exception, KeyboardInterrupt) as exc:
        manifest.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        if isinstance(exc, ExtractionError):
            manifest["window_audit"] = exc.window_audit
            manifest["coverage_gaps"] = [
                audit for audit in exc.window_audit if audit["status"] == "unresolved"
            ]
        else:
            reason = str(exc) or type(exc).__name__
            gap_id, gap_start, gap_end = active_window or ("w0001", start, end)
            gap = {
                "window_id": gap_id,
                "starttime": iso_utc(gap_start),
                "endtime": iso_utc(gap_end),
                "status": "unresolved",
                "reason": reason,
            }
            manifest["window_audit"] = [*windows, gap]
            manifest["coverage_gaps"] = [gap]
        save_manifest()
        raise
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch one bounded USGS earthquake batch.")
    parser.add_argument("--site", required=True, choices=sorted(SITES))
    parser.add_argument("--start", required=True, type=parse_utc, help="Inclusive ISO date/time (UTC if timezone omitted)")
    parser.add_argument("--end", required=True, type=parse_utc, help="Inclusive ISO date/time (UTC if timezone omitted)")
    parser.add_argument("--output", type=Path, default=Path("data/raw"), help="Output root (default: data/raw; ignored by Git)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        manifest = run_batch(args.site, args.start, args.end, args.output)
    except (ExtractionError, httpx.HTTPError, OSError) as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1
    summary = json.loads(manifest.read_text(encoding="utf-8"))
    print(f"Batch {summary['attempt_id']} saved: {manifest}")
    print(f"Source rows: {summary['source_rows_returned']}; raw rows written: {summary['raw_rows_written']}")
    print(f"Window status: {summary['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
