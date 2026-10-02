"""Offline guards for the isolated tombstone procedure call."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.fixture_deletion import (
    ATTEMPT_ID,
    EXPECTED_AFTER,
    UPDATE_COUNTS,
    UPDATE_PROCESS_ID,
    _guard_after,
    _guard_before,
    _guard_raw,
    execute_deletion,
    preview,
)
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE


class FixtureDeletionTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("scripts.evidence.phase2.fixture_deletion.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    def test_raw_guard_requires_deleted_source(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(RuntimeError, "RAW receipt"):
            _guard_raw(cursor)
        sql, params = cursor.execute.call_args.args
        self.assertIn(TEST_DATABASE + ".RAW.BATCH_ATTEMPT", sql)
        self.assertEqual(params, (ATTEMPT_ID,))

    def test_changed_update_state_stops_before_call(self):
        cursor = MagicMock()
        with patch("scripts.evidence.phase2.fixture_deletion._guard_raw", return_value="hash"), \
             patch("scripts.evidence.phase2.fixture_deletion._counts",
                   return_value={**UPDATE_COUNTS, "FACT_EVENT_REVISION": 3}):
            with self.assertRaisesRegex(RuntimeError, "measured update state"):
                _guard_before(cursor)

    def test_bad_outcome_stops_before_postqueries(self):
        cursor = MagicMock()
        with self.assertRaisesRegex(RuntimeError, "outcome differs"):
            _guard_after(cursor, {"attempt_id": ATTEMPT_ID, "status": "complete",
                                  "loaded_rows": 1, "processed_rows": 1,
                                  "rejected_rows": 0, "revision_rows_merged": 0,
                                  "process_attempt_id": "p"}, "hash")
        cursor.execute.assert_not_called()

    def test_good_outcome_requires_no_current_and_three_revisions(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        cursor.fetchall.side_effect = [
            [("reviewed", "old"), ("reviewed", "update"), ("deleted", "delete")],
            [("complete", 1)],
        ]
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 1, "processed_rows": 1,
                   "rejected_rows": 0, "revision_rows_merged": 1,
                   "process_attempt_id": "new-process"}
        with patch("scripts.evidence.phase2.fixture_deletion._counts", return_value=EXPECTED_AFTER), \
             patch("scripts.evidence.phase2.fixture_deletion._hash_feature",
                   side_effect=["old", "update"]), \
             patch("scripts.evidence.phase2.fixture_deletion._guard_unique_keys"):
            self.assertEqual(_guard_after(cursor, outcome, "delete"), EXPECTED_AFTER)

    def test_single_call_happens_after_preflight(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ('{"attempt_id":"fixture-deletion-v1"}',)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        with patch("scripts.evidence.phase2.fixture_deletion.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.fixture_deletion._guard_before",
                   side_effect=lambda *_: events.append("before") or "hash"), \
             patch("scripts.evidence.phase2.fixture_deletion._guard_after",
                   side_effect=lambda *_: events.append("after") or EXPECTED_AFTER):
            execute_deletion()
        self.assertEqual(events, ["before", "after"])
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("CALL ") for item in calls), 1)
        self.assertIn(TEST_DATABASE + ".CURATED.PROCESS_LOADED_ATTEMPT", calls[-1])
        self.assertNotEqual(UPDATE_PROCESS_ID, "new-process")


if __name__ == "__main__":
    unittest.main()
