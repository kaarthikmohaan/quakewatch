"""Mock transaction order and retry audit behavior without Snowflake."""

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from quakewatch.process_batch import BatchProjection
from quakewatch.process_transaction import process_loaded_attempt


class FakeFrame:
    def __init__(self, session, sql):
        self.session, self.sql = session, sql

    def collect(self):
        self.session.events.append(self.sql)
        if self.sql == "COMMIT" and self.session.fail_commit:
            raise RuntimeError("commit response lost")
        if self.sql == "ROLLBACK" and self.session.fail_rollback:
            raise RuntimeError("rollback response lost")
        return []


class FakeSession:
    def __init__(self, fail_commit=False, fail_rollback=False):
        self.events = []
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback

    def sql(self, query):
        return FakeFrame(self, query)


class FakeWriter:
    def __init__(self, fail=False):
        self.fail = fail
        self.successes = []
        self.failures = []

    def write_models(self, session, projection):
        session.events.append("write_models")
        if self.fail:
            raise ValueError("model merge failed")
        return 1

    def record_success(self, session, outcome):
        session.events.append("record_success")
        self.successes.append(outcome)

    def record_failure(self, session, outcome):
        session.events.append("record_failure")
        self.failures.append(outcome)


PROJECTION = BatchProjection("attempt-1", 2, 2, 1, ())
TIME = datetime(2026, 9, 30, tzinfo=UTC)


class ProcessTransactionTest(unittest.TestCase):
    @patch("quakewatch.process_transaction.read_and_project_attempt", return_value=PROJECTION)
    def test_success_log_is_inside_model_transaction(self, read):
        session, writer = FakeSession(), FakeWriter()
        outcome = process_loaded_attempt(
            session, "attempt-1", writer, make_id=lambda: "process-1", now=lambda: TIME
        )
        self.assertEqual(session.events,
                         ["BEGIN TRANSACTION", "write_models", "record_success", "COMMIT"])
        self.assertEqual((outcome.loaded_rows, outcome.processed_rows, outcome.rejected_rows),
                         (2, 2, 1))
        self.assertEqual(outcome.process_attempt_id, "process-1")
        self.assertEqual(len(writer.successes), 1)
        self.assertEqual(writer.failures, [])

    @patch("quakewatch.process_transaction.read_and_project_attempt", return_value=PROJECTION)
    def test_failed_write_rolls_back_then_appends_failure(self, read):
        session, writer = FakeSession(), FakeWriter(fail=True)
        with self.assertRaisesRegex(ValueError, "model merge failed"):
            process_loaded_attempt(session, "attempt-1", writer)
        self.assertEqual(session.events,
                         ["BEGIN TRANSACTION", "write_models", "ROLLBACK", "record_failure"])
        self.assertEqual(writer.failures[0].status, "failed")
        self.assertEqual(writer.successes, [])

    @patch("quakewatch.process_transaction.read_and_project_attempt", side_effect=ValueError("bad receipt"))
    def test_read_failure_is_logged_without_starting_transaction(self, read):
        session, writer = FakeSession(), FakeWriter()
        with self.assertRaisesRegex(ValueError, "bad receipt"):
            process_loaded_attempt(session, "attempt-1", writer)
        self.assertEqual(session.events, ["record_failure"])

    @patch("quakewatch.process_transaction.read_and_project_attempt", return_value=PROJECTION)
    def test_uncertain_commit_does_not_write_false_failure(self, read):
        session, writer = FakeSession(fail_commit=True), FakeWriter()
        with self.assertRaisesRegex(RuntimeError, "commit outcome unknown"):
            process_loaded_attempt(session, "attempt-1", writer)
        self.assertEqual(session.events[-1], "COMMIT")
        self.assertEqual(writer.failures, [])

    @patch("quakewatch.process_transaction.read_and_project_attempt", return_value=PROJECTION)
    def test_uncertain_rollback_does_not_claim_failed_audit(self, read):
        session, writer = FakeSession(fail_rollback=True), FakeWriter(fail=True)
        with self.assertRaisesRegex(RuntimeError, "rollback outcome unknown"):
            process_loaded_attempt(session, "attempt-1", writer)
        self.assertEqual(writer.failures, [])


if __name__ == "__main__":
    unittest.main()
