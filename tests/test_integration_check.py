"""The live integration check compiles every procedure and reviewed statement."""

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.checks import integration


class FakeCursor:
    def __init__(self, failing=()):
        self.failing, self.sql = failing, []

    def execute(self, sql, params=()):
        self.sql.append(sql)
        if any(marker in sql for marker in self.failing):
            raise RuntimeError("SQL compilation error:\ninvalid identifier 'X'")

    def fetchall(self):
        return []


class IntegrationCheckTest(unittest.TestCase):
    def test_collects_every_snowpark_statement_and_reviewed_query(self):
        procedure = integration.procedure_statements()
        self.assertGreaterEqual(len(procedure), 20)
        self.assertIn("snowpark_revision_write.MERGE_SQL", procedure)
        self.assertTrue(
            any(k.startswith("checks/uniqueness.sql") for k in integration.file_statements())
        )

    def test_every_statement_becomes_bind_free_explain(self):
        for sql in {**integration.procedure_statements(), **integration.file_statements()}.values():
            text = integration.explainable(sql)
            self.assertTrue(text.startswith("EXPLAIN USING TEXT "))
            self.assertNotIn("?", text)

    def test_compile_failures_are_all_reported(self):
        cursor = FakeCursor(failing=("FACT_EVENT_REVISION",))
        failures = integration.compile_all(cursor, integration.procedure_statements())
        self.assertGreater(len(failures), 1)
        self.assertTrue(all("invalid identifier" in f for f in failures))
        self.assertTrue(all(s.startswith("EXPLAIN") for s in cursor.sql))

    def test_preview_does_not_connect(self):
        with (
            patch.object(integration, "connect_project") as connect,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            integration.preview()
        connect.assert_not_called()
        self.assertIn("preview only", out.getvalue())


if __name__ == "__main__":
    unittest.main()
