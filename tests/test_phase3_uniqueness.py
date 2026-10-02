"""Offline guardrails for the read-only Phase 3 uniqueness runner."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.checks.phase3_uniqueness import (
    CHECKS,
    execute_checks,
    main,
    reviewed_statements,
)


class Phase3UniquenessRunnerTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase3_uniqueness.py"]), \
             patch("scripts.checks.phase3_uniqueness.connect_project",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertEqual(len(reviewed_statements()), 2)

    def test_changed_sql_stops_before_connection(self):
        with patch("scripts.checks.phase3_uniqueness.EXPECTED_SHA256", "wrong"), \
             patch("scripts.checks.phase3_uniqueness.connect_project") as connect:
            with self.assertRaisesRegex(ValueError, "SQL changed"):
                execute_checks()
        connect.assert_not_called()

    def test_zero_duplicate_groups_pass(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(0,), (0,)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.checks.phase3_uniqueness.connect_project", return_value=connection):
            result = execute_checks()
        self.assertEqual(result, {"status": "pass", "counts": dict.fromkeys(CHECKS, 0)})
        sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("SELECT COUNT(*) FROM (") for item in sql), 2)
        self.assertFalse(any(item.lstrip().startswith(("CALL ", "DELETE ", "MERGE "))
                             for item in sql))

    def test_duplicate_groups_fail(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(2,), (0,)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.checks.phase3_uniqueness.connect_project", return_value=connection):
            self.assertEqual(execute_checks()["status"], "fail")


if __name__ == "__main__":
    unittest.main()
