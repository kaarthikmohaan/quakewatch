"""Offline checks for bounded Cortex aggregate saving."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.evidence.phase4.cortex_aggregates import EXPECTED_CASES, save_aggregates

COLUMNS = [
    "CASE_ID", "SITE_KEY", "START_UTC", "END_UTC", "RADIUS_KM",
    "DISTINCT_RADII", "EVENT_COUNT", "NEAREST_EVENT_ID",
    "NEAREST_DISTANCE_KM", "NEAREST_MAGNITUDE", "NEAREST_SOURCE_STATUS",
    "NEAREST_RECORD_AGE_HOURS", "CHECKED_AT",
]


def rows() -> list[tuple]:
    return [
        (case_id, "san-francisco" if case_id.startswith("sf-") else
         "anchorage" if case_id.startswith("anchorage-") else "seattle",
         "2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z", 250.0, 1,
         1, f"event-{case_id}", 42.1, 1.23, "reviewed", 59.8,
         "2026-10-01T00:00:00Z")
        for case_id in sorted(EXPECTED_CASES)
    ]


class CortexAggregateTests(unittest.TestCase):
    def test_saves_only_ten_public_bounded_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "aggregates.json"
            document = save_aggregates(COLUMNS, rows(), "query-1", "SELECT 1", output)

            self.assertEqual(document["case_count"], 10)
            self.assertEqual(len({case["INPUT_SHA256"] for case in document["cases"]}), 10)
            self.assertEqual(json.loads(output.read_text())["query_id"], "query-1")
            self.assertNotIn("LONGITUDE", output.read_text())
            self.assertNotIn("LATITUDE", output.read_text())

    def test_rejects_missing_case_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "aggregates.json"
            with self.assertRaisesRegex(RuntimeError, "ten expected cases"):
                save_aggregates(COLUMNS, rows()[:-1], "query-1", "SELECT 1", output)
            self.assertFalse(output.exists())
