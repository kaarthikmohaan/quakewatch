"""Deterministic candidate deduplication before a revision fact MERGE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class RevisionCandidate:
    canonical_event_id: str
    source_updated_at: datetime
    payload_hash: str
    fetched_at: datetime
    stage_file_name: str
    stage_file_row_number: int

    @property
    def revision_key(self) -> tuple[str, datetime, str]:
        return (self.canonical_event_id, self.source_updated_at, self.payload_hash)

    @property
    def source_key(self) -> tuple[str, int]:
        return (self.stage_file_name, self.stage_file_row_number)


def deduplicate_revision_candidates(
    candidates: Iterable[RevisionCandidate],
) -> list[RevisionCandidate]:
    """Keep one reproducible observation per logical revision identity.

    Alias resolution supplies ``canonical_event_id`` before this function runs.
    A different payload at the same update time remains a distinct revision.
    """
    by_source: dict[tuple[str, int], RevisionCandidate] = {}
    by_revision: dict[tuple[str, datetime, str], RevisionCandidate] = {}
    for candidate in candidates:
        if not candidate.canonical_event_id or not candidate.payload_hash:
            raise ValueError("revision candidate requires canonical ID and payload hash")
        if candidate.source_updated_at.tzinfo is None or candidate.fetched_at.tzinfo is None:
            raise ValueError("revision candidate timestamps must be timezone-aware")
        if not candidate.stage_file_name or candidate.stage_file_row_number < 1:
            raise ValueError("revision candidate requires a staged file-row key")
        existing_source = by_source.get(candidate.source_key)
        if existing_source is not None and existing_source != candidate:
            raise ValueError("conflicting observations share a staged file-row key")
        by_source[candidate.source_key] = candidate
        previous = by_revision.get(candidate.revision_key)
        if previous is None or (
            candidate.fetched_at, candidate.stage_file_name, candidate.stage_file_row_number
        ) > (
            previous.fetched_at, previous.stage_file_name, previous.stage_file_row_number
        ):
            by_revision[candidate.revision_key] = candidate
    return [by_revision[key] for key in sorted(by_revision)]
