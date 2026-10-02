"""Offline guardrails for one idempotent processing rerun."""

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.evidence.phase2.rerun_check import (
    ATTEMPT_ID,
    BASE_COUNTS,
    FIRST_PROCESS_ID,
    _guard_after,
    _guard_before,
    _guard_unique_keys,
    preview,
)


class FakeCursor:
    def __init__(self, rows=(), duplicate_count=0, rows_by_fragment=None):
        self.rows = list(rows)
        self.duplicate_count = duplicate_count
        self.rows_by_fragment = rows_by_fragment or {}
        self.calls = []
        self.query = ""

    def execute(self, query, params=None):
        self.query = query
        self.calls.append((query, params))

    def fetchall(self):
        for fragment, rows in self.rows_by_fragment.items():
            if fragment in self.query:
                return rows
        return self.rows

    def fetchone(self):
        return (self.duplicate_count,)


class RerunCheckTest(unittest.TestCase):
    def test_preview_never_connects(self):
        output = io.StringIO()
        with patch("scripts.evidence.phase2.rerun_check.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    @patch("scripts.evidence.phase2.rerun_check._guard_unique_keys")
    @patch("scripts.evidence.phase2.rerun_check._model_counts", return_value=BASE_COUNTS)
    @patch("scripts.evidence.phase2.rerun_check._guard_receipt")
    def test_first_pilot_state_is_required(self, receipt, counts, unique):
        cursor = FakeCursor(rows=[(FIRST_PROCESS_ID, "complete", 15, 15, 0, 15)])
        with self.assertRaisesRegex(RuntimeError, "batch fact"):
            _guard_before(cursor)
        receipt.assert_called_once_with(cursor)
        unique.assert_not_called()

    @patch("scripts.evidence.phase2.rerun_check._model_counts", return_value=BASE_COUNTS)
    def test_rerun_must_merge_zero_revisions(self, counts):
        cursor = FakeCursor()
        with self.assertRaisesRegex(RuntimeError, "did not converge"):
            _guard_after(cursor, {"attempt_id": ATTEMPT_ID, "status": "complete",
                                  "loaded_rows": 15, "processed_rows": 15,
                                  "rejected_rows": 0, "revision_rows_merged": 1})
        self.assertEqual(cursor.calls, [])

    def test_duplicate_grain_key_stops(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate grain keys"):
            _guard_unique_keys(FakeCursor(duplicate_count=1))

    @patch("scripts.evidence.phase2.rerun_check._guard_unique_keys")
    @patch("scripts.evidence.phase2.rerun_check._model_counts",
           return_value={**BASE_COUNTS, "BATCH_PROCESS_ATTEMPT": 2})
    def test_complete_rerun_keeps_model_counts_and_new_audit(self, counts, unique):
        cursor = FakeCursor(rows_by_fragment={
            "WHERE PROCESS_ATTEMPT_ID": [("complete", 15, 15, 0, 0)],
            "FROM QUAKEWATCH.CURATED.FACT_BATCH_RUN": [("complete", "process-2")],
        })
        outcome = {"attempt_id": ATTEMPT_ID, "status": "complete",
                   "loaded_rows": 15, "processed_rows": 15, "rejected_rows": 0,
                   "revision_rows_merged": 0, "process_attempt_id": "process-2"}
        self.assertEqual(_guard_after(cursor, outcome)["BATCH_PROCESS_ATTEMPT"], 2)
        unique.assert_called_once_with(cursor)


if __name__ == "__main__":
    unittest.main()
