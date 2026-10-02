"""Mock bounded staging MERGEs and reconciliation without Snowflake."""

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from quakewatch.process_batch import RawObservation, project_raw_attempt
from quakewatch.snowpark_staging_write import write_staging
from quakewatch.staging import STAGING_PARSER_VERSION

FEATURE = json.loads((Path(__file__).parent / "fixtures/normal_event.json").read_text())


class FakeRow:
    def __init__(self, values):
        self.values = values

    def as_dict(self):
        return self.values


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return [FakeRow(row) for row in self.rows]


class FakeSession:
    def __init__(self, existing=None, final_count=0):
        self.existing = existing or []
        self.final_count = final_count
        self.calls = []

    def sql(self, query, params):
        self.calls.append((query, params))
        if "SELECT STAGE_FILE_NAME" in query:
            return FakeFrame(self.existing)
        if "SELECT COUNT(*)" in query:
            return FakeFrame([{"ROW_COUNT": self.final_count}])
        return FakeFrame([])


def projection(n=1):
    base = RawObservation("attempt-1", "w0001", "attempt-1/events.jsonl", 1,
                          datetime(2026, 9, 30, tzinfo=UTC), "a" * 64, "1", FEATURE)
    return project_raw_attempt(
        [replace(base, stage_file_row_number=i + 1) for i in range(n)], "attempt-1", n
    )


class StagingWriteTest(unittest.TestCase):
    def test_merges_bounded_json_groups_and_checks_count(self):
        session = FakeSession(final_count=3)
        with patch("quakewatch.snowpark_staging_write.MAX_ROWS_PER_MERGE", 2):
            self.assertEqual(write_staging(session, projection(3)), 3)
        merges = [(sql, params) for sql, params in session.calls if "MERGE INTO" in sql]
        self.assertEqual(len(merges), 2)
        self.assertEqual([len(json.loads(params[0])) for _, params in merges], [2, 1])
        self.assertEqual(json.loads(merges[0][1][0])[0]["source_event_id"], FEATURE["id"])
        self.assertIn("WHEN NOT MATCHED THEN INSERT", merges[0][0])

    def test_existing_same_source_row_is_idempotent(self):
        p = projection()
        session = FakeSession(existing=[dict(
            STAGE_FILE_NAME="attempt-1/events.jsonl", STAGE_FILE_ROW_NUMBER=1,
            ATTEMPT_ID="attempt-1", PAYLOAD_HASH="a" * 64,
            RAW_PARSER_VERSION="1", STAGING_PARSER_VERSION=STAGING_PARSER_VERSION,
        )], final_count=1)
        self.assertEqual(write_staging(session, p), 1)

    def test_existing_hash_conflict_stops_before_merge(self):
        session = FakeSession(existing=[dict(
            STAGE_FILE_NAME="attempt-1/events.jsonl", STAGE_FILE_ROW_NUMBER=1,
            ATTEMPT_ID="attempt-1", PAYLOAD_HASH="b" * 64,
            RAW_PARSER_VERSION="1", STAGING_PARSER_VERSION=STAGING_PARSER_VERSION,
        )])
        with self.assertRaisesRegex(ValueError, "conflicts"):
            write_staging(session, projection())
        self.assertFalse(any("MERGE INTO" in sql for sql, _ in session.calls))

    def test_final_count_mismatch_fails_transaction(self):
        with self.assertRaisesRegex(ValueError, "staging row count"):
            write_staging(FakeSession(final_count=0), projection())


if __name__ == "__main__":
    unittest.main()
