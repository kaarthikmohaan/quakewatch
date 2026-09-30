"""Mock revision MERGE key, deduplication, and count checks."""

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.process_batch import RawObservation, project_raw_attempt
from quakewatch.snowpark_revision_write import write_revision_fact


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
    def __init__(self, duplicates=False, prior_alias=None):
        self.calls = []
        self.duplicates = duplicates
        self.prior_alias = prior_alias

    def sql(self, query, params):
        self.calls.append((query, params))
        if "MERGE INTO" in query:
            return FakeFrame([{"number of rows inserted": len(json.loads(params[0])),
                               "number of rows updated": 0}])
        if "SELECT DISTINCT SOURCE_EVENT_ID" in query:
            return FakeFrame([self.prior_alias] if self.prior_alias else [])
        return FakeFrame([{"DUPLICATES": 2}] if self.duplicates else [])


def projection(*features):
    base = RawObservation("attempt-1", "w0001", "attempt-1/events.jsonl", 1,
                          datetime(2026, 9, 30, tzinfo=UTC), "a" * 64, "1", FEATURE)
    return project_raw_attempt([
        replace(base, stage_file_row_number=i + 1, payload=feature)
        for i, feature in enumerate(features)
    ], "attempt-1", len(features))


class RevisionWriteTest(unittest.TestCase):
    def test_repeated_revision_is_deduped_before_merge(self):
        session = FakeSession()
        changed = write_revision_fact(
            session, projection(FEATURE, FEATURE), {FEATURE["id"]: "canonical-1"}
        )
        self.assertEqual(changed, 1)
        merge = next((query, params) for query, params in session.calls if "MERGE INTO" in query)
        self.assertEqual(len(json.loads(merge[1][0])), 1)
        self.assertIn("t.CANONICAL_EVENT_ID = s.CANONICAL_EVENT_ID", merge[0])
        self.assertIn("t.PAYLOAD_HASH = s.PAYLOAD_HASH", merge[0])

    def test_rejects_never_enter_fact(self):
        bad = {**FEATURE, "id": ""}
        session = FakeSession()
        self.assertEqual(write_revision_fact(session, projection(bad), {}), 0)
        self.assertEqual(session.calls, [])

    def test_missing_canonical_map_stops_before_sql(self):
        session = FakeSession()
        with self.assertRaisesRegex(ValueError, "canonical ID missing"):
            write_revision_fact(session, projection(FEATURE), {})
        self.assertEqual(session.calls, [])

    def test_duplicate_target_key_fails_transaction(self):
        with self.assertRaisesRegex(ValueError, "duplicate canonical"):
            write_revision_fact(FakeSession(duplicates=True), projection(FEATURE),
                                {FEATURE["id"]: "canonical-1"})

    def test_new_alias_requires_rekey_before_merge(self):
        session = FakeSession(prior_alias={
            "SOURCE_EVENT_ID": FEATURE["id"], "CANONICAL_EVENT_ID": "old-canonical",
        })
        with self.assertRaisesRegex(ValueError, "alias rekey required"):
            write_revision_fact(session, projection(FEATURE),
                                {FEATURE["id"]: "new-canonical"})
        self.assertFalse(any("MERGE INTO" in sql for sql, _ in session.calls))


if __name__ == "__main__":
    unittest.main()
