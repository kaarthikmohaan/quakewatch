"""Offline safeguards for the isolated fixture deployment."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.phase2_fixture_deploy import (
    BUNDLE_SHA256, PACKAGE_CHECK_SQL, _guard_empty, _guard_package,
    ddl_statements, execute_deploy, preview,
)
from scripts.phase2_fixture_namespace import TEST_DATABASE


class FixtureDeployTest(unittest.TestCase):
    def test_preview_is_offline_and_artifacts_are_current(self):
        output = io.StringIO()
        with patch("scripts.phase2_fixture_deploy.connect_project",
                   side_effect=AssertionError("connected")), contextlib.redirect_stdout(output):
            preview()
        self.assertEqual(len(ddl_statements()), 16)
        self.assertIn(BUNDLE_SHA256, output.getvalue())
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertFalse(any("CALL " in statement for statement in ddl_statements()))

    def test_stale_generated_sql_stops_before_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.phase2_fixture_deploy.DEFAULT_OUTPUT", Path(directory)), \
                 patch("scripts.phase2_fixture_deploy.BUNDLE", Path(directory) / "missing.zip"):
                with self.assertRaisesRegex(ValueError, "ZIP missing"):
                    ddl_statements()

    def test_nonempty_schema_stops(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[], [("existing",)]]
        with self.assertRaisesRegex(RuntimeError, "not empty"):
            _guard_empty(cursor)
        self.assertEqual(cursor.execute.call_count, 2)

    def test_package_must_be_available(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        with self.assertRaisesRegex(RuntimeError, "absent"):
            _guard_package(cursor)
        cursor.execute.assert_called_once_with(PACKAGE_CHECK_SQL)

    def test_deploy_runs_only_after_guards_and_new_upload(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("status",)]
        cursor.fetchone.return_value = ("UPLOADED",)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        def guard_empty(_cursor):
            events.append("empty")
        def guard_package(_cursor):
            events.append("package")
        with patch("scripts.phase2_fixture_deploy.connect_project", return_value=connection), \
             patch("scripts.phase2_fixture_deploy._guard_empty", side_effect=guard_empty), \
             patch("scripts.phase2_fixture_deploy._guard_package", side_effect=guard_package):
            outcome = execute_deploy()
        self.assertEqual(events, ["empty", "package"])
        self.assertEqual(outcome["database"], TEST_DATABASE)
        self.assertEqual(outcome["ddl_statements_executed"], 16)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(statements[3].startswith("CREATE STAGE " + TEST_DATABASE))
        self.assertTrue(statements[4].startswith("PUT 'file:"))
        self.assertFalse(any(statement.startswith("CALL ") for statement in statements))


if __name__ == "__main__":
    unittest.main()
