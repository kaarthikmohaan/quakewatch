"""Check the bounded pilot plan without contacting Snowflake."""

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.phase2_pilot import (
    ATTEMPT_ID, DDL_FILES, _guard_empty_curated, _guard_receipt,
    ddl_statements, preview,
)


class FakeCursor:
    def __init__(self, show_rows=None, receipt_rows=None, raw_count=15):
        self.calls = []
        self.show_rows = show_rows or {}
        self.receipt_rows = receipt_rows if receipt_rows is not None else [
            ("complete", "complete", 15, 15, 15, 0)
        ]
        self.raw_count = raw_count
        self.query = ""
        self.description = [("name",)]

    def execute(self, query, params=None):
        self.query = query
        self.calls.append((query, params))

    def fetchone(self):
        if self.query.startswith("SHOW"):
            return self.show_rows.get(self.query)
        return (self.raw_count,)

    def fetchall(self):
        if self.query.startswith("SHOW"):
            row = self.show_rows.get(self.query)
            return [row] if row is not None else []
        return self.receipt_rows


class Phase2PilotTest(unittest.TestCase):
    def test_preview_is_offline_and_names_one_bounded_attempt(self):
        output = io.StringIO()
        with patch("scripts.phase2_pilot.connect_project", side_effect=AssertionError(
            "preview connected"
        )), contextlib.redirect_stdout(output):
            preview()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    def test_ddl_order_and_procedure_body_survive_split(self):
        statements = ddl_statements()
        self.assertEqual(len(DDL_FILES), 6)
        self.assertEqual(sum("CREATE OR REPLACE PROCEDURE" in s for s in statements), 1)
        self.assertIn("CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.STG_EVENT_REVISION",
                      statements[0])
        self.assertIn("from quakewatch.snowpark_procedure import run", statements[-1])

    def test_preflight_rejects_existing_curated_objects(self):
        cursor = FakeCursor(show_rows={"SHOW TABLES IN SCHEMA QUAKEWATCH.CURATED": ("old",)})
        with self.assertRaisesRegex(RuntimeError, "already has tables"):
            _guard_empty_curated(cursor)

    def test_preflight_uses_user_procedures_to_exclude_builtins(self):
        cursor = FakeCursor()
        _guard_empty_curated(cursor)
        self.assertEqual(cursor.calls[-1][0],
                         "SHOW USER PROCEDURES IN SCHEMA QUAKEWATCH.CURATED")

    def test_preflight_rejects_bad_receipt_or_raw_count(self):
        for cursor in (FakeCursor(receipt_rows=[]), FakeCursor(raw_count=14)):
            with self.subTest(cursor=cursor), self.assertRaises(RuntimeError):
                _guard_receipt(cursor)


if __name__ == "__main__":
    unittest.main()
