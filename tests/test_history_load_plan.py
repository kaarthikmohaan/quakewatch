"""Offline tests for the local history load candidate inventory."""

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from quakewatch.history_load_plan import check_snowflake, classify_loads, load_candidates


class HistoryLoadPlanTests(unittest.TestCase):
    def test_classification_requires_matching_receipt_and_raw_rows(self) -> None:
        candidates = [
            (number, {"attempt_id": str(number), "expected_rows": 10}) for number in range(1, 6)
        ]
        receipts = [
            ("1", "complete", 10),
            ("3", "failed", 0),
            ("4", "complete", 9),
            ("5", "complete", 10),
            ("5", "complete", 10),
        ]
        raw_counts = [("1", 10), ("3", 2), ("4", 10), ("5", 10)]
        self.assertEqual(
            [row[2] for row in classify_loads(candidates, receipts, raw_counts)],
            ["loaded", "ready", "investigate", "investigate", "investigate"],
        )

    def test_account_check_uses_bound_ids_and_read_only_queries(self) -> None:
        candidates = [(1, {"attempt_id": "first", "expected_rows": 10})]
        cursor = FakeCursor()
        result = check_snowflake(candidates, FakeConnection(cursor))
        self.assertEqual(result[0][2], "loaded")
        self.assertEqual(len(cursor.commands), 2)
        self.assertTrue(all(params == ("first",) for _, params in cursor.commands))
        self.assertTrue(all(sql.startswith("SELECT") for sql, _ in cursor.commands))
        self.assertTrue(cursor.closed)

    def test_validates_candidates_without_account_connection(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "attempt" / "manifest.json"
            path.parent.mkdir()
            with patch(
                "quakewatch.history_load_plan.captured_history_windows", return_value={2: path}
            ):
                with patch(
                    "quakewatch.history_load_plan.plan_raw_load",
                    return_value={"attempt_id": "attempt", "expected_rows": 185},
                ) as plan:
                    self.assertEqual(
                        load_candidates(cutoff, Path(folder)),
                        [(2, {"attempt_id": "attempt", "expected_rows": 185})],
                    )
            plan.assert_called_once_with(path)

    def test_no_candidates_returns_empty_list(self) -> None:
        with TemporaryDirectory() as folder:
            self.assertEqual(load_candidates(datetime(2026, 9, 29, tzinfo=UTC), Path(folder)), [])


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class FakeCursor:
    def __init__(self):
        self.commands = []
        self.closed = False

    def execute(self, sql, params):
        self.commands.append((sql, params))

    def fetchall(self):
        if len(self.commands) == 1:
            return [("first", "complete", 10)]
        return [("first", 10)]

    def close(self):
        self.closed = True
