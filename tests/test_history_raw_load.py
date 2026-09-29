"""Offline tests for the bounded history RAW loader."""

import unittest
from unittest.mock import patch

from quakewatch.history_raw_load import load_ready


class HistoryRawLoadTests(unittest.TestCase):
    def test_skips_loaded_and_limits_ready_attempts(self) -> None:
        candidates = [(n, {"attempt_id": str(n), "expected_rows": n * 10}) for n in range(1, 5)]
        initial = [(1, candidates[0][1], "loaded"),
                   (2, candidates[1][1], "ready"),
                   (3, candidates[2][1], "ready"),
                   (4, candidates[3][1], "ready")]
        with patch("quakewatch.history_raw_load.check_snowflake",
                   side_effect=[initial, [initial[1]], [initial[2]]]) as check:
            with patch("quakewatch.history_raw_load.execute_raw_load",
                       side_effect=[20, 30]) as execute:
                self.assertEqual(load_ready(candidates, object(), 2), [2, 3])
        self.assertEqual(check.call_count, 3)
        self.assertEqual(execute.call_count, 2)

    def test_investigate_blocks_all_loads(self) -> None:
        candidates = [(1, {"attempt_id": "1", "expected_rows": 10})]
        with patch("quakewatch.history_raw_load.check_snowflake",
                   return_value=[(1, candidates[0][1], "investigate")]):
            with patch("quakewatch.history_raw_load.execute_raw_load") as execute:
                with self.assertRaisesRegex(RuntimeError, "no RAW loads started"):
                    load_ready(candidates, object(), 1)
        execute.assert_not_called()

    def test_changed_status_blocks_copy(self) -> None:
        candidates = [(1, {"attempt_id": "1", "expected_rows": 10})]
        with patch("quakewatch.history_raw_load.check_snowflake",
                   side_effect=[[(1, candidates[0][1], "ready")],
                                [(1, candidates[0][1], "loaded")]]):
            with patch("quakewatch.history_raw_load.execute_raw_load") as execute:
                with self.assertRaisesRegex(RuntimeError, "stop before PUT/COPY"):
                    load_ready(candidates, object(), 1)
        execute.assert_not_called()

    def test_invalid_limit_blocks_account_work(self) -> None:
        with patch("quakewatch.history_raw_load.check_snowflake") as check:
            with self.assertRaisesRegex(ValueError, "between 1 and 50"):
                load_ready([], object(), 51)
        check.assert_not_called()
