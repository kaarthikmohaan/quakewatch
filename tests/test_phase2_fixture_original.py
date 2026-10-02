"""Offline guards for one original-event procedure call in the test database."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.fixture_original import (
    ATTEMPT_ID,
    EVENT_ID,
    EXPECTED_AFTER,
    _guard_after,
    _guard_before,
    _guard_raw,
    execute_original,
    preview,
)
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE


class FixtureOriginalTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("scripts.evidence.phase2.fixture_original.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    def test_raw_guard_requires_synthetic_complete_row(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(RuntimeError, "RAW receipt"):
            _guard_raw(cursor)
        query, params = cursor.execute.call_args.args
        self.assertIn(TEST_DATABASE + ".RAW.BATCH_ATTEMPT", query)
        self.assertEqual(params, (ATTEMPT_ID,))

    def test_curated_must_be_empty_before_call(self):
        cursor = MagicMock()
        with patch("scripts.evidence.phase2.fixture_original._guard_raw", return_value="hash"), \
             patch("scripts.evidence.phase2.fixture_original._counts",
                   return_value={"FACT_EVENT_REVISION": 1}):
            with self.assertRaisesRegex(RuntimeError, "must be empty"):
                _guard_before(cursor)

    def test_bad_outcome_stops_before_postqueries(self):
        cursor = MagicMock()
        with self.assertRaisesRegex(RuntimeError, "outcome differs"):
            _guard_after(cursor, {"attempt_id": ATTEMPT_ID, "status": "complete",
                                  "loaded_rows": 1, "processed_rows": 1,
                                  "rejected_rows": 0, "revision_rows_merged": 0,
                                  "process_attempt_id": "p"}, "hash")
        cursor.execute.assert_not_called()

    def test_good_outcome_checks_current_and_audit(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(EVENT_ID, EVENT_ID, "reviewed", 1.08, "hash")],
            [("complete", 1, 1, 0, 1)],
        ]
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 1, "processed_rows": 1,
                   "rejected_rows": 0, "revision_rows_merged": 1,
                   "process_attempt_id": "p"}
        with patch("scripts.evidence.phase2.fixture_original._counts", return_value=EXPECTED_AFTER), \
             patch("scripts.evidence.phase2.fixture_original._guard_unique_keys") as unique:
            self.assertEqual(_guard_after(cursor, outcome, "hash"), EXPECTED_AFTER)
        unique.assert_called_once_with(cursor)

    def test_single_call_happens_after_preflight(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ('{"attempt_id":"fixture-original-v1"}',)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        with patch("scripts.evidence.phase2.fixture_original.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.fixture_original._guard_before",
                   side_effect=lambda *_: events.append("before") or "hash"), \
             patch("scripts.evidence.phase2.fixture_original._guard_after",
                   side_effect=lambda *_: events.append("after") or EXPECTED_AFTER):
            execute_original()
        self.assertEqual(events, ["before", "after"])
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("CALL ") for item in calls), 1)
        self.assertIn(TEST_DATABASE + ".CURATED.PROCESS_LOADED_ATTEMPT", calls[-1])


if __name__ == "__main__":
    unittest.main()
