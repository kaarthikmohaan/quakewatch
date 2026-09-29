"""Offline tests for the local history load candidate inventory."""

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from quakewatch.history_load_plan import load_candidates


class HistoryLoadPlanTests(unittest.TestCase):
    def test_validates_candidates_without_account_connection(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "attempt" / "manifest.json"
            path.parent.mkdir()
            with patch("quakewatch.history_load_plan.captured_history_windows", return_value={2: path}):
                with patch("quakewatch.history_load_plan.plan_raw_load",
                           return_value={"attempt_id": "attempt", "expected_rows": 185}) as plan:
                    self.assertEqual(load_candidates(cutoff, Path(folder)),
                                     [(2, {"attempt_id": "attempt", "expected_rows": 185})])
            plan.assert_called_once_with(path)

    def test_no_candidates_returns_empty_list(self) -> None:
        with TemporaryDirectory() as folder:
            self.assertEqual(load_candidates(datetime(2026, 9, 29, tzinfo=UTC), Path(folder)), [])
