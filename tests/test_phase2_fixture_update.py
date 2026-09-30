"""Offline guards for the later synthetic update procedure call."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.phase2_fixture_namespace import TEST_DATABASE
from scripts.phase2_fixture_update import (
    ATTEMPT_ID, EXPECTED_AFTER, ORIGINAL_COUNTS, ORIGINAL_PROCESS_ID,
    _guard_after, _guard_before, _guard_raw, execute_update, preview,
)


class FixtureUpdateTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("scripts.phase2_fixture_update.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    def test_raw_guard_rejects_missing_update(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(RuntimeError, "RAW receipt"):
            _guard_raw(cursor)
        sql, params = cursor.execute.call_args.args
        self.assertIn(TEST_DATABASE + ".RAW.BATCH_ATTEMPT", sql)
        self.assertEqual(params, (ATTEMPT_ID,))

    def test_changed_baseline_stops_before_call(self):
        cursor = MagicMock()
        with patch("scripts.phase2_fixture_update._guard_raw", return_value="hash"), \
             patch("scripts.phase2_fixture_update._counts",
                   return_value={**ORIGINAL_COUNTS, "FACT_EVENT_REVISION": 2}):
            with self.assertRaisesRegex(RuntimeError, "measured original state"):
                _guard_before(cursor)

    def test_bad_outcome_stops_before_postqueries(self):
        cursor = MagicMock()
        with self.assertRaisesRegex(RuntimeError, "outcome differs"):
            _guard_after(cursor, {"attempt_id": ATTEMPT_ID, "status": "complete",
                                  "loaded_rows": 1, "processed_rows": 1,
                                  "rejected_rows": 0, "revision_rows_merged": 0,
                                  "process_attempt_id": "p"}, "hash")
        cursor.execute.assert_not_called()

    def test_good_outcome_requires_two_revisions_and_new_current(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [("reviewed", 1.08, "old"), ("reviewed", 1.28, "new")],
            [("complete", 1)],
        ]
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 1, "processed_rows": 1,
                   "rejected_rows": 0, "revision_rows_merged": 1,
                   "process_attempt_id": "new-process"}
        with patch("scripts.phase2_fixture_update._counts", return_value=EXPECTED_AFTER), \
             patch("scripts.phase2_fixture_update._current",
                   return_value=[("uw714110682", "reviewed", 1.28, "new")]), \
             patch("scripts.phase2_fixture_update._hash_feature", return_value="old") as hashes, \
             patch("scripts.phase2_fixture_update._guard_unique_keys"):
            # The fixture hash helper is called for the historical original.
            self.assertEqual(_guard_after(cursor, outcome, "new"), EXPECTED_AFTER)
        hashes.assert_called_once()

    def test_single_call_happens_after_preflight(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ('{"attempt_id":"fixture-update-v1"}',)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        with patch("scripts.phase2_fixture_update.connect_project", return_value=connection), \
             patch("scripts.phase2_fixture_update._guard_before",
                   side_effect=lambda *_: events.append("before") or "hash"), \
             patch("scripts.phase2_fixture_update._guard_after",
                   side_effect=lambda *_: events.append("after") or EXPECTED_AFTER):
            execute_update()
        self.assertEqual(events, ["before", "after"])
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("CALL ") for item in calls), 1)
        self.assertIn(TEST_DATABASE + ".CURATED.PROCESS_LOADED_ATTEMPT", calls[-1])
        self.assertNotEqual(ORIGINAL_PROCESS_ID, "new-process")


if __name__ == "__main__":
    unittest.main()
