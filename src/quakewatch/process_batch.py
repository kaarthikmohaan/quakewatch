"""One-attempt RAW projection core for the in-Snowflake procedure."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quakewatch.staging import project_feature


@dataclass(frozen=True)
class RawObservation:
    attempt_id: str
    window_id: str
    stage_file_name: str
    stage_file_row_number: int
    fetched_at: datetime
    payload_hash: str
    raw_parser_version: str
    payload: Any

    @property
    def source_key(self) -> tuple[str, int]:
        return (self.stage_file_name, self.stage_file_row_number)


@dataclass(frozen=True)
class ProjectedObservation:
    raw: RawObservation
    fields: dict[str, Any]


@dataclass(frozen=True)
class BatchProjection:
    attempt_id: str
    loaded_rows: int
    processed_rows: int
    rejected_rows: int
    observations: tuple[ProjectedObservation, ...]


def project_raw_attempt(
    rows: Iterable[RawObservation], attempt_id: str, expected_loaded_rows: int
) -> BatchProjection:
    """Validate RAW lineage/counts, then project every row including rejects.

    The caller must read a complete load receipt first. A mismatch fails the
    whole transform before any staged or curated table is changed.
    """
    if not attempt_id or expected_loaded_rows < 0:
        raise ValueError("attempt ID and nonnegative loaded row count are required")
    projected: list[ProjectedObservation] = []
    seen_source_keys: set[tuple[str, int]] = set()
    for row in rows:
        if row.attempt_id != attempt_id:
            raise ValueError("RAW row belongs to a different attempt")
        if not row.window_id or not row.stage_file_name or row.stage_file_row_number < 1:
            raise ValueError("RAW row lacks a valid source file-row key")
        if row.source_key in seen_source_keys:
            raise ValueError("duplicate RAW staged file-row key")
        seen_source_keys.add(row.source_key)
        if row.fetched_at.tzinfo is None or not row.payload_hash or not row.raw_parser_version:
            raise ValueError("RAW row lacks capture metadata")
        projected.append(ProjectedObservation(row, project_feature(row.payload)))
    if len(projected) != expected_loaded_rows:
        raise ValueError("RAW row count does not match the complete load receipt")
    rejected = sum(item.fields["reject_reason"] is not None for item in projected)
    return BatchProjection(
        attempt_id=attempt_id,
        loaded_rows=expected_loaded_rows,
        processed_rows=len(projected),
        rejected_rows=rejected,
        observations=tuple(projected),
    )
