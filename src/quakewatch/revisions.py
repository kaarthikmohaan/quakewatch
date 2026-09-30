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


@dataclass(frozen=True)
class RevisionState(RevisionCandidate):
    origin_time: datetime
    source_status: str


def latest_revision_by_event(revisions: Iterable[RevisionState]) -> dict[str, RevisionState]:
    """Select the newest revision, including a latest deleted tombstone."""
    latest: dict[str, RevisionState] = {}
    for revision in revisions:
        if not revision.canonical_event_id or not revision.source_status:
            raise ValueError("current revision requires canonical ID and source status")
        if any(
            clock.tzinfo is None
            for clock in (revision.origin_time, revision.source_updated_at, revision.fetched_at)
        ):
            raise ValueError("current revision timestamps must be timezone-aware")
        previous = latest.get(revision.canonical_event_id)
        rank = (
            revision.source_updated_at, revision.fetched_at, revision.payload_hash,
            revision.stage_file_name, revision.stage_file_row_number,
        )
        if previous is None or rank > (
            previous.source_updated_at, previous.fetched_at, previous.payload_hash,
            previous.stage_file_name, previous.stage_file_row_number,
        ):
            latest[revision.canonical_event_id] = revision
    return latest


def visible_current_revisions(revisions: Iterable[RevisionState]) -> dict[str, RevisionState]:
    """Hide an event only when its latest revision is a deleted tombstone."""
    return {
        event_id: revision
        for event_id, revision in latest_revision_by_event(revisions).items()
        if revision.source_status != "deleted"
    }
