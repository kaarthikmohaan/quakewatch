"""Mock successful batch-fact MERGE and receipt guardrails."""

import json
import unittest
from datetime import UTC, datetime, timedelta

from quakewatch.process_batch import BatchProjection
from quakewatch.snowpark_batch_fact_write import write_successful_batch_fact

NOW = datetime(2026, 9, 30, tzinfo=UTC)


class FakeRow:
    def __init__(self, fields):
        self.fields = fields

    def as_dict(self):
        return self.fields


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return [FakeRow(row) for row in self.rows]


class FakeSession:
    def __init__(self, receipt=None, existing=None):
        self.calls = []
        self.receipt = [receipt] if receipt is not None else []
        self.existing = existing or []

    def sql(self, query, params):
        self.calls.append((query, params))
        if "FROM QUAKEWATCH.RAW.BATCH_ATTEMPT" in query:
            return FakeFrame(self.receipt)
        if "FROM QUAKEWATCH.CURATED.FACT_BATCH_RUN" in query:
            return FakeFrame(self.existing)
        return FakeFrame([])


def receipt(**overrides):
    values = {
        "ATTEMPT_ID": "attempt-1", "LOGICAL_BATCH_ID": "batch-1",
        "BATCH_KIND": "history", "SITE_KEY": "seattle",
        "REQUESTED_STARTTIME": NOW - timedelta(days=1),
        "REQUESTED_ENDTIME": NOW, "FETCHED_AT": NOW,
        "RECORDED_AT": NOW, "SOURCE_ROWS_RETURNED": 3,
        "RAW_ROWS_WRITTEN": 3, "LOADED_ROWS": 3,
        "EXTRACT_STATUS": "complete", "LOAD_STATUS": "complete",
        "COVERAGE_GAPS": [],
    }
    return {**values, **overrides}


PROJECTION = BatchProjection("attempt-1", 3, 3, 1, ())


class BatchFactWriteTest(unittest.TestCase):
    def test_success_keeps_source_counts_separate_from_rejects(self):
        session = FakeSession(receipt())
        write_successful_batch_fact(session, PROJECTION, "process-1",
                                    NOW + timedelta(seconds=2))
        sql, params = session.calls[-1]
        row = json.loads(params[0])[0]
        self.assertIn("ON t.ATTEMPT_ID = s.ATTEMPT_ID", sql)
        self.assertEqual((row["source_rows_returned"], row["raw_rows_written"],
                          row["loaded_rows"], row["processed_rows"], row["rejected_rows"]),
                         (3, 3, 3, 3, 1))
        self.assertEqual(row["fetch_to_curated_seconds"], 2.0)
        self.assertEqual(row["last_process_attempt_id"], "process-1")

    def test_incomplete_receipt_stops_before_merge(self):
        for changed in ({"LOADED_ROWS": 2}, {"COVERAGE_GAPS": ["w1"]},
                        {"LOAD_STATUS": "failed"}):
            session = FakeSession(receipt(**changed))
            with self.subTest(changed=changed), self.assertRaisesRegex(
                ValueError, "not complete and reconciled"
            ):
                write_successful_batch_fact(session, PROJECTION, "process-1", NOW)
            self.assertFalse(any("MERGE INTO" in sql for sql, _ in session.calls))

    def test_duplicate_or_conflicting_target_stops_before_merge(self):
        for prior in ([{"LOGICAL_BATCH_ID": "batch-1"}] * 2,
                      [{"LOGICAL_BATCH_ID": "different"}]):
            session = FakeSession(receipt(), prior)
            with self.assertRaisesRegex(ValueError, "key conflicts"):
                write_successful_batch_fact(session, PROJECTION, "process-1", NOW)
            self.assertFalse(any("MERGE INTO" in sql for sql, _ in session.calls))


if __name__ == "__main__":
    unittest.main()
