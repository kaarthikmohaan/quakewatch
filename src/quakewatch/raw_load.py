"""Local safeguards before and after a Snowflake RAW copy."""

import json
from pathlib import Path
from typing import Any


class LoadReconciliationError(ValueError):
    """A batch cannot be marked loaded because its counts or source disagree."""


def validate_local_batch(manifest_path: Path) -> tuple[dict[str, Any], int]:
    """Check a completed attempt and its JSONL file before staging it."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or manifest.get("coverage_gaps"):
        raise LoadReconciliationError("attempt is incomplete or has coverage gaps")

    events_name = manifest.get("events_file")
    if events_name != "events.jsonl":
        raise LoadReconciliationError("unexpected events file name")
    events_path = manifest_path.parent / events_name
    if not events_path.is_file():
        raise LoadReconciliationError("events file is missing")

    count = 0
    with events_path.open(encoding="utf-8") as stream:
        for line in stream:
            count += 1
            try:
                record = json.loads(line)
                metadata = record["metadata"]
                if not isinstance(record["source_feature"], dict) or any(
                    metadata[field] != manifest[field]
                    for field in ("logical_batch_id", "attempt_id", "fetched_at")
                ):
                    raise ValueError("record does not match manifest")
                for field in ("window_id", "payload_hash", "parser_version"):
                    if not metadata[field]:
                        raise ValueError(f"missing {field}")
            except (ValueError, KeyError, TypeError) as exc:
                raise LoadReconciliationError(f"invalid events row {count}: {exc}") from exc

    if not count == manifest.get("source_rows_returned") == manifest.get("raw_rows_written"):
        raise LoadReconciliationError("manifest and local events row counts disagree")
    return manifest, count


def reconcile_loaded_rows(expected: int, copy_rows: int, raw_rows: int) -> None:
    """Require both Snowflake counts to match the validated local attempt."""
    if min(expected, copy_rows, raw_rows) < 0 or expected != copy_rows or expected != raw_rows:
        raise LoadReconciliationError(
            f"row counts disagree (local={expected}, copied={copy_rows}, raw={raw_rows})"
        )
