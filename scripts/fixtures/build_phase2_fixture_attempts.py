"""Build four ignored, synthetic RAW attempts for the isolated test database."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quakewatch.raw_load import validate_local_batch
from scripts.pipeline.build_procedure_bundle import REPO_ROOT

OUTPUT_ROOT = REPO_ROOT / "data" / "procedure" / "phase2_fixture" / "attempts"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SEQUENCE = (
    ("fixture-original-v1", "normal_event.json"),
    ("fixture-update-v1", "synthetic_revision_event.json"),
    ("fixture-deletion-v1", "synthetic_tombstone_event.json"),
    ("fixture-stale-replay-v1", "normal_event.json"),
)
FETCH_BASE = datetime(2026, 9, 30, 0, 0, tzinfo=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_once(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"existing fixture file differs; stop before overwrite: {path}")
        return
    path.write_text(content, encoding="utf-8")


def build_attempts(
    output_root: Path = OUTPUT_ROOT,
    sequence: tuple[tuple[str, str], ...] = SEQUENCE,
    fetch_base: datetime = FETCH_BASE,
) -> list[dict]:
    """Write deterministic local fixtures; make no source or Snowflake request."""
    summaries = []
    for index, (attempt_id, fixture_name) in enumerate(sequence):
        feature = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
        payload_hash = hashlib.sha256(json.dumps(
            feature, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        fetched_at = _iso(fetch_base + timedelta(minutes=index))
        logical_batch_id = attempt_id
        source_day = datetime.fromtimestamp(feature["properties"]["time"] / 1000, tz=UTC)
        start = source_day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        manifest = {
            "logical_batch_id": logical_batch_id,
            "attempt_id": attempt_id,
            "batch_kind": "synthetic_fixture",
            "fixture_only": True,
            "fixture_source": fixture_name,
            "site": {"name": "Seattle", "latitude": 47.6062,
                     "longitude": -122.3321, "radius_km": 250.0},
            "requested_starttime": _iso(start),
            "requested_endtime": _iso(end),
            "query_parameters": {"source": "local_synthetic_fixture", "fixture": fixture_name},
            "fetched_at": fetched_at,
            "window_audit": [{"window_id": "w0001", "status": "synthetic_fixture",
                              "fixture_rows": 1}],
            "coverage_gaps": [],
            "source_rows_returned": 1,
            "raw_rows_written": 1,
            "events_file": "events.jsonl",
            "status": "complete",
        }
        record = {
            "source_feature": feature,
            "metadata": {
                "logical_batch_id": logical_batch_id,
                "attempt_id": attempt_id,
                "window_id": "w0001",
                "fetched_at": fetched_at,
                "payload_hash": payload_hash,
                "parser_version": "1",
                "fixture_only": True,
            },
        }
        directory = output_root / attempt_id
        directory.mkdir(parents=True, exist_ok=True)
        _write_once(directory / "manifest.json", json.dumps(manifest, indent=2) + "\n")
        _write_once(directory / "events.jsonl", json.dumps(record, separators=(",", ":")) + "\n")
        validate_local_batch(directory / "manifest.json")
        summaries.append({"attempt_id": attempt_id, "fixture": fixture_name,
                          "rows": 1, "payload_hash": payload_hash})
    return summaries


def main() -> None:
    summaries = build_attempts()
    print("Phase 2 synthetic fixture attempts: local files only; no USGS or Snowflake request")
    for item in summaries:
        print(f"{item['attempt_id']}: {item['fixture']}, {item['rows']} row")
    print(f"Output: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
