"""Offline checks for the read-only old-origin completion audit."""

import unittest
from unittest.mock import MagicMock, patch

from scripts.phase2_old_origin_final_check import verify
from scripts.phase2_old_origin_update import EXPECTED_AFTER


class OldOriginFinalCheckTest(unittest.TestCase):
    def test_requires_both_complete_attempts_then_delegates_full_guard(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("fixture-old-origin-original-v1", "p1", "complete", 1, 1, 0, 1),
            ("fixture-old-origin-update-v1", "p2", "complete", 1, 1, 0, 1),
        ]
        with patch("scripts.phase2_old_origin_final_check._guard_raw"), \
             patch("scripts.phase2_old_origin_final_check._expected_hash",
                   return_value="new"), \
             patch("scripts.phase2_old_origin_final_check._guard_after",
                   return_value=EXPECTED_AFTER) as after:
            report = verify(cursor)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["old_origin_revisions"], 2)
        after.assert_called_once()
        outcome = after.call_args.args[1]
        self.assertEqual(outcome["attempt_id"], "fixture-old-origin-update-v1")
        self.assertEqual(outcome["process_attempt_id"], "p2")
        self.assertEqual(after.call_args.args[3], "p1")
        self.assertFalse(any(call.args[0].startswith("CALL ")
                             for call in cursor.execute.call_args_list))

    def test_missing_update_stops_before_model_queries(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("fixture-old-origin-original-v1", "p1", "complete", 1, 1, 0, 1),
        ]
        with patch("scripts.phase2_old_origin_final_check._guard_raw"), \
             patch("scripts.phase2_old_origin_final_check._guard_after") as after:
            with self.assertRaisesRegex(RuntimeError, "exactly two"):
                verify(cursor)
        after.assert_not_called()


if __name__ == "__main__":
    unittest.main()
