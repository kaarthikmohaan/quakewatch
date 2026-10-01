"""Offline checks for first-ever fixture transform failure and retry."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.phase2_first_failure_demo import ATTEMPT_ID, _plan, execute, main


class FirstFailureDemoTest(unittest.TestCase):
    def test_preview_builds_only_local_fixture(self):
        output = io.StringIO()
        with patch("scripts.phase2_first_failure_demo.connect_project",
                   side_effect=AssertionError("connected")), \
             patch("sys.argv", ["phase2_first_failure_demo.py"]), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())
        self.assertEqual(_plan()["manifest"]["source_rows_returned"], 1)

    def test_existing_attempt_stops_before_put_or_call(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [("existing",)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.phase2_first_failure_demo.connect_project", return_value=connection), \
             patch("scripts.phase2_first_failure_demo._snapshot",
                   return_value={"raw": 1, "receipts": 1}):
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                execute()
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any(text.startswith(("PUT ", "COPY ", "CALL ")) for text in statements))


if __name__ == "__main__":
    unittest.main()
