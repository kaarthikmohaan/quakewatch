"""Offline guards for the isolated failed-transform/retry drill."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.phase2_recovery_demo import CREATE_SQL, ATTEMPT_ID, execute, main


class RecoveryDemoTest(unittest.TestCase):
    def test_preview_never_connects(self):
        output = io.StringIO()
        with patch("scripts.evidence.phase2.phase2_recovery_demo.connect_project",
                   side_effect=AssertionError("connected")), \
             patch("sys.argv", ["phase2_recovery_demo.py"]), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(ATTEMPT_ID, output.getvalue())

    def test_failure_procedure_is_fixture_only_and_rolls_back_after_writes(self):
        self.assertIn("QUAKEWATCH_PHASE2_FIXTURE.CURATED", CREATE_SQL)
        self.assertNotIn("QUAKEWATCH.CURATED.", CREATE_SQL)
        self.assertNotIn("QUAKEWATCH.RAW.", CREATE_SQL)
        self.assertIn("super().write_models(session, projection)", CREATE_SQL)
        self.assertIn("raise ValueError", CREATE_SQL)
        self.assertIn("process_loaded_attempt(session, attempt_id", CREATE_SQL)
        self.assertNotIn("CREATE OR REPLACE", CREATE_SQL)

    def test_wrong_raw_count_stops_before_procedure_creation(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.evidence.phase2.phase2_recovery_demo.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.phase2_recovery_demo._snapshot",
                   return_value={"raw": 0, "receipts": 1}):
            with self.assertRaisesRegex(RuntimeError, "expected one-row load"):
                execute()
        self.assertFalse(any(call.args[0] == CREATE_SQL for call in cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
