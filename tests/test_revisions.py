"""Duplicate and distinct-revision cases before the Snowflake MERGE."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from quakewatch.revisions import RevisionCandidate, deduplicate_revision_candidates


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


if __name__ == "__main__":
    unittest.main()
