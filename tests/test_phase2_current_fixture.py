"""Offline guards for the isolated current-view Snowflake fixture."""

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.phase2_current_fixture import (
    _assert_state, feature_row, preview, view_select_sql,
)


TABLE = "QUAKEWATCH.CURATED.QW_CURRENT_FIXTURE_" + "A" * 32


class FakeCursor:
    def __init__(self, rows, count):
        self.rows = rows
        self.count = count
        self.query = ""

    def execute(self, query):
        self.query = query

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return (self.count,)


class CurrentFixtureTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("scripts.phase2_current_fixture.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())

    def test_view_query_uses_only_isolated_table(self):
        query = view_select_sql(TABLE)
        self.assertIn(f"FROM {TABLE} FACT_EVENT_REVISION", query)
        self.assertNotIn("FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION", query)
        self.assertIn("WHERE REVISION_RANK = 1 AND SOURCE_STATUS <> 'deleted'", query)
        with self.assertRaisesRegex(ValueError, "invalid temporary"):
            view_select_sql("QUAKEWATCH.CURATED.FACT_EVENT_REVISION")

    def test_fixture_order_and_shared_identity(self):
        first = feature_row("normal_event.json")
        updated = feature_row("synthetic_revision_event.json")
        deleted = feature_row("synthetic_tombstone_event.json")
        self.assertEqual({row[0] for row in (first, updated, deleted)}, {"uw714110682"})
        self.assertEqual({row[4] for row in (first, updated, deleted)}, {first[4]})
        self.assertLess(first[1], updated[1])
        self.assertLess(updated[1], deleted[1])
        self.assertEqual([row[7] for row in (first, updated, deleted)],
                         ["reviewed", "reviewed", "deleted"])

    def test_assert_state_checks_current_and_history(self):
        query = view_select_sql(TABLE)
        cursor = FakeCursor([("uw714110682", "reviewed", 1.28)], 2)
        _assert_state(cursor, query, 2, [("uw714110682", "reviewed", 1.28)])
        cursor.count = 3
        with self.assertRaisesRegex(RuntimeError, "revision count mismatch"):
            _assert_state(cursor, query, 2, [("uw714110682", "reviewed", 1.28)])
        cursor.rows = []
        with self.assertRaisesRegex(RuntimeError, "current-view fixture mismatch"):
            _assert_state(cursor, query, 2, [("uw714110682", "reviewed", 1.28)])


if __name__ == "__main__":
    unittest.main()
