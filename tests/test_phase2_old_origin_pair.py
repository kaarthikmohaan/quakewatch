"""Offline guards for the combined old-origin procedure calls."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.old_origin_pair import execute_pair, main
from scripts.evidence.phase2.old_origin_update import (
    ATTEMPT_ID,
    EXPECTED_AFTER,
    ORIGINAL_COUNTS,
    _guard_after,
    _guard_before,
    _original_process_id,
    execute_update,
)
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE


class OldOriginPairTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase2_old_origin_pair.py"]), \
             patch("scripts.evidence.phase2.old_origin_pair.connect_project",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn("update call runs only after", output.getvalue())

    def test_update_guard_requires_original_state(self):
        cursor = MagicMock()
        with patch("scripts.evidence.phase2.old_origin_update._guard_raw"), \
             patch("scripts.evidence.phase2.old_origin_update._counts",
                   return_value={**ORIGINAL_COUNTS, "FACT_EVENT_REVISION": 5}):
            with self.assertRaisesRegex(RuntimeError, "old-origin original state"):
                _guard_before(cursor, "original-process")

    def test_recovery_discovers_exact_original_process_id(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [("original-process", "complete", 1)]
        self.assertEqual(_original_process_id(cursor), "original-process")
        cursor.fetchall.return_value = [("original-process", "failed", 0)]
        with self.assertRaisesRegex(RuntimeError, "processing audit differs"):
            _original_process_id(cursor)

    def test_recovery_calls_only_update_after_discovering_original_id(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ('{"attempt_id":"fixture-old-origin-update-v1"}',)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.evidence.phase2.old_origin_update.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.old_origin_update._original_process_id",
                   return_value="original-process"), \
             patch("scripts.evidence.phase2.old_origin_update._guard_before", return_value="new") as before, \
             patch("scripts.evidence.phase2.old_origin_update._guard_after", return_value=EXPECTED_AFTER):
            execute_update()
        before.assert_called_once_with(cursor, "original-process")
        calls = [call.args for call in cursor.execute.call_args_list
                 if call.args[0].startswith("CALL ")]
        self.assertEqual(calls, [
            (f"CALL {TEST_DATABASE}.CURATED.PROCESS_LOADED_ATTEMPT(%s)",
             ("fixture-old-origin-update-v1",)),
        ])

    def test_update_after_requires_current_and_both_revisions(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [("qw-old-origin-001", "reviewed", 1.3, "new", "2020-01-15")],
            [("reviewed", 1.1, "old", "2020-01-15"),
             ("reviewed", 1.3, "new", "2020-01-15")],
            [("complete", 1)],
        ]
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 1, "processed_rows": 1, "rejected_rows": 0,
                   "revision_rows_merged": 1, "process_attempt_id": "update-process"}
        with patch("scripts.evidence.phase2.old_origin_update._counts", return_value=EXPECTED_AFTER), \
             patch("scripts.evidence.phase2.old_origin_update._expected_hash", return_value="old"), \
             patch("scripts.evidence.phase2.old_origin_update._guard_unique_keys"):
            self.assertEqual(_guard_after(cursor, outcome, "new", "original-process"),
                             EXPECTED_AFTER)

    def test_pair_calls_in_order_after_guards(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            ('{"attempt_id":"fixture-old-origin-original-v1","process_attempt_id":"p1"}',),
            ('{"attempt_id":"fixture-old-origin-update-v1","process_attempt_id":"p2"}',),
        ]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        with patch("scripts.evidence.phase2.old_origin_pair.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.old_origin_pair.original_before",
                   side_effect=lambda *_: events.append("original before") or "old"), \
             patch("scripts.evidence.phase2.old_origin_pair.original_after",
                   side_effect=lambda *_: events.append("original after") or {}), \
             patch("scripts.evidence.phase2.old_origin_pair.update_before",
                   side_effect=lambda *_: events.append("update before") or "new"), \
             patch("scripts.evidence.phase2.old_origin_pair.update_after",
                   side_effect=lambda *_: events.append("update after") or {}), \
             contextlib.redirect_stdout(io.StringIO()):
            execute_pair()
        self.assertEqual(events, ["original before", "original after",
                                  "update before", "update after"])
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual([call for call in calls if call.startswith("CALL ")], [
            f"CALL {TEST_DATABASE}.CURATED.PROCESS_LOADED_ATTEMPT(%s)",
            f"CALL {TEST_DATABASE}.CURATED.PROCESS_LOADED_ATTEMPT(%s)",
        ])
        self.assertEqual([call.args[1] for call in cursor.execute.call_args_list
                          if call.args[0].startswith("CALL ")],
                         [("fixture-old-origin-original-v1",),
                          ("fixture-old-origin-update-v1",)])

    def test_second_call_skipped_if_first_check_fails(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ('{"process_attempt_id":"p1"}',)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.evidence.phase2.old_origin_pair.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.old_origin_pair.original_before", return_value="old"), \
             patch("scripts.evidence.phase2.old_origin_pair.original_after",
                   side_effect=RuntimeError("first check failed")), \
             patch("scripts.evidence.phase2.old_origin_pair.update_before") as second:
            with self.assertRaisesRegex(RuntimeError, "first check failed"):
                execute_pair()
        second.assert_not_called()
        self.assertEqual(sum(call.args[0].startswith("CALL ")
                             for call in cursor.execute.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
