"""Offline guards for the isolated stale-replay procedure call."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.phase2_fixture_stale_replay import (
    ATTEMPT_ID, DELETION_COUNTS, EXPECTED_AFTER,
    _guard_after, _guard_before, execute_stale_replay, preview,
)
from scripts.phase2_fixture_namespace import TEST_DATABASE


class FixtureStaleReplayTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("scripts.phase2_fixture_stale_replay.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    def test_wrong_raw_receipt_stops_before_call(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(RuntimeError, "RAW receipt"):
            _guard_before(cursor)
        sql, params = cursor.execute.call_args.args
        self.assertIn(TEST_DATABASE + ".RAW.BATCH_ATTEMPT", sql)
        self.assertEqual(params, (ATTEMPT_ID,))

    def test_changed_deletion_state_stops_before_call(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [("complete", "complete", 1, 1, 1, 0,
                                         True, "old", "uw714110682", "reviewed")]
        with patch("scripts.phase2_fixture_stale_replay._expected_history",
                   return_value=[("reviewed", "old")]), \
             patch("scripts.phase2_fixture_stale_replay._counts",
                   return_value={**DELETION_COUNTS, "FACT_EVENT_REVISION": 4}):
            with self.assertRaisesRegex(RuntimeError, "measured deletion state"):
                _guard_before(cursor)

    def test_replay_must_not_resurrect_event(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 1, "processed_rows": 1, "rejected_rows": 0,
                   "revision_rows_merged": 1, "process_attempt_id": "new-process"}
        with patch("scripts.phase2_fixture_stale_replay._counts", return_value=EXPECTED_AFTER):
            with self.assertRaisesRegex(RuntimeError, "resurrected"):
                _guard_after(cursor, outcome, "old")

    def test_good_replay_preserves_history_and_audit(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        cursor.fetchall.side_effect = [
            [("reviewed", "old"), ("reviewed", "update"), ("deleted", "delete")],
            [("complete", 1)],
        ]
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 1, "processed_rows": 1, "rejected_rows": 0,
                   "revision_rows_merged": 1, "process_attempt_id": "new-process"}
        with patch("scripts.phase2_fixture_stale_replay._counts", return_value=EXPECTED_AFTER), \
             patch("scripts.phase2_fixture_stale_replay._expected_history",
                   return_value=[("reviewed", "old"), ("reviewed", "update"),
                                 ("deleted", "delete")]), \
             patch("scripts.phase2_fixture_stale_replay._guard_unique_keys"):
            self.assertEqual(_guard_after(cursor, outcome, "old"), EXPECTED_AFTER)

    def test_single_call_happens_after_preflight(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ('{"attempt_id":"fixture-stale-replay-v1"}',)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        with patch("scripts.phase2_fixture_stale_replay.connect_project", return_value=connection), \
             patch("scripts.phase2_fixture_stale_replay._guard_before",
                   side_effect=lambda *_: events.append("before") or "old"), \
             patch("scripts.phase2_fixture_stale_replay._guard_after",
                   side_effect=lambda *_: events.append("after") or EXPECTED_AFTER):
            execute_stale_replay()
        self.assertEqual(events, ["before", "after"])
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("CALL ") for item in calls), 1)
        self.assertIn(TEST_DATABASE + ".CURATED.PROCESS_LOADED_ATTEMPT", calls[-1])


if __name__ == "__main__":
    unittest.main()
