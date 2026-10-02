"""Offline guards for the proposed one-time Snowflake fixture setup."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.phase2_fixture_setup import (
    EXPECTED,
    execute_setup,
    main,
    setup_statements,
)


class FixtureSetupTest(unittest.TestCase):
    def test_preview_does_not_connect_and_sql_is_exact(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase2_fixture_setup.py"]), \
             patch("snowflake.connector.connect", side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        self.assertEqual(setup_statements(), EXPECTED)
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn("reviewed SQL statements: 12", output.getvalue())

    def test_changed_setup_sql_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "altered.sql"
            path.write_text("USE ROLE ACCOUNTADMIN; DROP DATABASE QUAKEWATCH;")
            with patch("scripts.evidence.phase2.phase2_fixture_setup.SETUP_FILE", path):
                with self.assertRaisesRegex(ValueError, "differs"):
                    setup_statements()

    def test_occupied_name_stops_before_ddl(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.evidence.phase2.phase2_fixture_setup.admin_params", return_value={}), \
             patch("snowflake.connector.connect", return_value=connection), \
             patch("scripts.evidence.phase2.phase2_fixture_setup.name_occupied", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                execute_setup(Path("unused"))
        cursor.execute.assert_not_called()

    def test_free_name_executes_only_reviewed_statements_then_verifies(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("name",)]
        cursor.fetchall.return_value = [("RAW",), ("CURATED",)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.evidence.phase2.phase2_fixture_setup.admin_params", return_value={}), \
             patch("snowflake.connector.connect", return_value=connection), \
             patch("scripts.evidence.phase2.phase2_fixture_setup.name_occupied", side_effect=[False, True]):
            result = execute_setup(Path("unused"))
        self.assertEqual(result["statements_executed"], len(EXPECTED))
        self.assertEqual([call.args[0] for call in cursor.execute.call_args_list[:len(EXPECTED)]],
                         list(EXPECTED))


if __name__ == "__main__":
    unittest.main()
