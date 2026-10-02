"""Mock append-only processing outcome writes."""

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime

from quakewatch.process_transaction import ProcessOutcome
from quakewatch.snowpark_process_log import append_process_outcome

TIME = datetime(2026, 9, 30, tzinfo=UTC)
SUCCESS = ProcessOutcome("process-1", "attempt-1", TIME, TIME, "complete", 3, 3, 1, 2)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows


class FakeSession:
    def __init__(self, existing=False):
        self.existing = existing
        self.calls = []

    def sql(self, query, params):
        self.calls.append((query, params))
        if "WHERE PROCESS_ATTEMPT_ID = ?" in query:
            return FakeFrame([object()] if self.existing else [])
        return FakeFrame([])


class ProcessLogTest(unittest.TestCase):
    def test_success_insert_uses_bound_outcome(self):
        session = FakeSession()
        append_process_outcome(session, SUCCESS)
        sql, params = session.calls[-1]
        self.assertIn("INSERT INTO QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT", sql)
        row = json.loads(params[0])[0]
        self.assertEqual(
            (row["status"], row["rejected_rows"], row["revision_rows_merged"]), ("complete", 1, 2)
        )
        self.assertIsNone(row["error_type"])

    def test_failed_retry_gets_separate_id_and_error(self):
        session = FakeSession()
        failure = replace(
            SUCCESS,
            process_attempt_id="process-2",
            status="failed",
            revision_rows_merged=0,
            error_type="ValueError",
            error_message="bad receipt",
        )
        append_process_outcome(session, failure)
        row = json.loads(session.calls[-1][1][0])[0]
        self.assertEqual(
            (row["process_attempt_id"], row["status"], row["error_type"]),
            ("process-2", "failed", "ValueError"),
        )

    def test_duplicate_id_stops_before_insert(self):
        session = FakeSession(existing=True)
        with self.assertRaisesRegex(ValueError, "already recorded"):
            append_process_outcome(session, SUCCESS)
        self.assertEqual(len(session.calls), 1)

    def test_invalid_status_counts_and_times_stop_before_sql(self):
        for invalid in (
            replace(SUCCESS, status="pending"),
            replace(SUCCESS, rejected_rows=4),
            replace(SUCCESS, finished_at=TIME.replace(tzinfo=None)),
        ):
            session = FakeSession()
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                append_process_outcome(session, invalid)
            self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
