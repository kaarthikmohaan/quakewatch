"""Mock dimension and event-site bridge writes without a Snowflake account."""

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.process_batch import RawObservation, project_raw_attempt
from quakewatch.snowpark_dimensions_write import write_dimensions_and_bridge

FEATURE = json.loads((Path(__file__).parent / "fixtures/normal_event.json").read_text())


class FakeFrame:
    def __init__(self, rows=None):
        self.rows = rows or []

    def collect(self):
        return self.rows


class FakeSession:
    def __init__(self, duplicate=False):
        self.calls = []
        self.duplicate = duplicate

    def sql(self, query, params):
        self.calls.append((query, params))
        if "HAVING COUNT(*) > 1" in query and self.duplicate:
            return FakeFrame([object()])
        return FakeFrame()


def projection(*features):
    base = RawObservation("attempt-1", "w0001", "attempt-1/events.jsonl", 1,
                          datetime(2026, 9, 30, tzinfo=UTC), "a" * 64, "1", FEATURE)
    return project_raw_attempt([
        replace(base, stage_file_row_number=i + 1, payload=feature)
        for i, feature in enumerate(features)
    ], "attempt-1", len(features))


class DimensionsWriteTest(unittest.TestCase):
    def test_one_revision_gets_three_public_site_rows(self):
        session = FakeSession()
        count = write_dimensions_and_bridge(
            session, projection(FEATURE), {FEATURE["id"]: "canonical-1"}
        )
        self.assertEqual(count, 3)
        bridge = next((sql, params) for sql, params in session.calls
                      if "MERGE INTO QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE" in sql)
        rows = json.loads(bridge[1][0])
        self.assertEqual({row["site_key"] for row in rows},
                         {"seattle", "san-francisco", "anchorage"})
        self.assertTrue(rows[0]["epicentral_distance_km"] >= 0)
        self.assertIn("t.PAYLOAD_HASH = s.PAYLOAD_HASH", bridge[0])
        self.assertEqual(sum("MERGE INTO QUAKEWATCH.CURATED.DIM_" in sql
                             for sql, _ in session.calls), 4)

    def test_deleted_without_geometry_has_null_bridge_values(self):
        deleted = json.loads((Path(__file__).parent / "fixtures/deleted_event.json").read_text())
        deleted["geometry"] = None
        session = FakeSession()
        self.assertEqual(write_dimensions_and_bridge(
            session, projection(deleted), {deleted["id"]: deleted["id"]}
        ), 3)
        body = next(params[0] for sql, params in session.calls
                    if "MERGE INTO QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE" in sql)
        self.assertTrue(all(row["epicentral_distance_km"] is None
                            and row["within_radius"] is None for row in json.loads(body)))

    def test_repeated_revision_does_not_duplicate_bridge_source(self):
        session = FakeSession()
        self.assertEqual(write_dimensions_and_bridge(
            session, projection(FEATURE, FEATURE), {FEATURE["id"]: "canonical-1"}
        ), 3)

    def test_existing_duplicate_bridge_key_fails(self):
        with self.assertRaisesRegex(ValueError, "duplicate event-site"):
            write_dimensions_and_bridge(
                FakeSession(duplicate=True), projection(FEATURE),
                {FEATURE["id"]: "canonical-1"}
            )


if __name__ == "__main__":
    unittest.main()
