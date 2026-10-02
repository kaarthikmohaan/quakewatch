"""Mock durable alias reads across old and current accepted observations."""

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.process_batch import RawObservation, project_raw_attempt
from quakewatch.snowpark_alias_read import resolve_durable_aliases

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
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def sql(self, query):
        self.queries.append(query)
        return FakeFrame(self.rows)


def projection(feature=FEATURE):
    raw = RawObservation(
        "attempt-1",
        "w1",
        "a/events.jsonl",
        1,
        datetime(2026, 9, 30, tzinfo=UTC),
        "a" * 64,
        "1",
        feature,
    )
    return project_raw_attempt([raw], "attempt-1", 1)


class AliasReadTest(unittest.TestCase):
    def test_old_and_current_ids_form_one_component(self):
        new = {
            **FEATURE,
            "id": "us-new",
            "properties": {**FEATURE["properties"], "ids": ",us-old,us-new,"},
        }
        session = FakeSession(
            [
                {"SOURCE_EVENT_ID": "us-old", "ASSOCIATED_IDS": '["us-old"]'},
                {"SOURCE_EVENT_ID": "us-new", "ASSOCIATED_IDS": ["us-old", "us-new"]},
            ]
        )
        self.assertEqual(
            resolve_durable_aliases(session, projection(new)),
            {"us-new": "us-new", "us-old": "us-new"},
        )
        self.assertIn("REJECT_REASON IS NULL", session.queries[0])

    def test_missing_current_observation_stops(self):
        with self.assertRaisesRegex(ValueError, "missing from durable"):
            resolve_durable_aliases(FakeSession([]), projection())

    def test_malformed_stored_aliases_stop(self):
        session = FakeSession(
            [{"SOURCE_EVENT_ID": FEATURE["id"], "ASSOCIATED_IDS": '{"wrong":true}'}]
        )
        with self.assertRaisesRegex(ValueError, "array of non-empty"):
            resolve_durable_aliases(session, projection())

    def test_rejected_current_row_needs_no_alias(self):
        invalid = {**FEATURE, "id": ""}
        self.assertEqual(resolve_durable_aliases(FakeSession([]), projection(invalid)), {})


if __name__ == "__main__":
    unittest.main()
