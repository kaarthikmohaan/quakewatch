"""Duplicate and distinct-revision cases before the Snowflake MERGE."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from quakewatch.revisions import (
    RevisionCandidate,
    RevisionState,
    deduplicate_revision_candidates,
    latest_revision_by_event,
    visible_current_revisions,
)


UPDATED = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)


def candidate(**changes: object) -> RevisionCandidate:
    base = RevisionCandidate(
        canonical_event_id="event-1",
        source_updated_at=UPDATED,
        payload_hash="a" * 64,
        fetched_at=UPDATED + timedelta(minutes=1),
        stage_file_name="attempt-a/events.jsonl",
        stage_file_row_number=1,
    )
    return replace(base, **changes)


class RevisionDedupeTest(unittest.TestCase):
    def test_overlap_keeps_one_deterministic_candidate(self) -> None:
        first = candidate()
        repeat = candidate(
            fetched_at=UPDATED + timedelta(minutes=2),
            stage_file_name="attempt-b/events.jsonl",
        )
        self.assertEqual(deduplicate_revision_candidates([first, repeat]), [repeat])
        self.assertEqual(deduplicate_revision_candidates([repeat, first]), [repeat])

    def test_different_payload_or_update_remains_a_revision(self) -> None:
        first = candidate()
        new_payload = candidate(payload_hash="b" * 64, stage_file_row_number=2)
        later_update = candidate(
            source_updated_at=UPDATED + timedelta(minutes=1), stage_file_row_number=3
        )
        self.assertEqual(
            len(deduplicate_revision_candidates([first, new_payload, later_update])), 3
        )

    def test_aliases_already_resolved_to_one_canonical_key(self) -> None:
        preferred = candidate(stage_file_name="preferred/events.jsonl")
        alias = candidate(stage_file_name="alias/events.jsonl", fetched_at=UPDATED)
        self.assertEqual(deduplicate_revision_candidates([alias, preferred]), [preferred])

    def test_conflicting_unseen_file_row_is_rejected(self) -> None:
        first = candidate()
        conflict = candidate(payload_hash="b" * 64)
        with self.assertRaisesRegex(ValueError, "conflicting observations"):
            deduplicate_revision_candidates([first, conflict])


def state(**changes: object) -> RevisionState:
    base = RevisionState(
        **candidate().__dict__,
        origin_time=datetime(2021, 9, 29, tzinfo=UTC),
        source_status="reviewed",
    )
    return replace(base, **changes)


class CurrentRevisionTest(unittest.TestCase):
    def test_newest_tombstone_hides_event_even_after_stale_replay(self) -> None:
        old = state()
        deleted = state(
            source_updated_at=UPDATED + timedelta(minutes=2),
            fetched_at=UPDATED + timedelta(minutes=3),
            payload_hash="b" * 64,
            source_status="deleted",
        )
        self.assertEqual(latest_revision_by_event([old, deleted])["event-1"], deleted)
        self.assertEqual(visible_current_revisions([old, deleted, old]), {})
        self.assertEqual(visible_current_revisions([deleted, old]), {})

    def test_update_of_old_origin_event_is_current(self) -> None:
        old = state(origin_time=datetime(2010, 1, 1, tzinfo=UTC))
        updated = state(
            origin_time=old.origin_time,
            source_updated_at=UPDATED + timedelta(days=1),
            payload_hash="b" * 64,
        )
        self.assertEqual(visible_current_revisions([old, updated])["event-1"], updated)

    def test_fetch_time_then_hash_break_equal_update_ties(self) -> None:
        old_fetch = state()
        new_fetch = state(fetched_at=UPDATED + timedelta(minutes=2))
        self.assertEqual(latest_revision_by_event([new_fetch, old_fetch])["event-1"], new_fetch)
        larger_hash = state(fetched_at=new_fetch.fetched_at, payload_hash="f" * 64)
        self.assertEqual(latest_revision_by_event([new_fetch, larger_hash])["event-1"], larger_hash)

    def test_tombstone_does_not_hide_unrelated_event(self) -> None:
        deleted = state(source_status="deleted")
        other = state(canonical_event_id="event-2", stage_file_row_number=2)
        self.assertEqual(visible_current_revisions([deleted, other]), {"event-2": other})


if __name__ == "__main__":
    unittest.main()
