"""Guard bounded history processing before and after each procedure call."""

import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.pipeline.process_history import main, process_history


class Phase3ProcessHistoryTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with (
            patch("sys.argv", ["phase3_process_history.py"]),
            patch(
                "scripts.pipeline.process_history.connect_project",
                side_effect=AssertionError("connected"),
            ),
            contextlib.redirect_stdout(output),
        ):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())

    def test_exact_pending_batch_runs_once_and_checks_health(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            [("attempt-1", 2)],
            [("PENDING_PROCESS", 2, 2, 0, None, None)],
            [("RECONCILED", 2, 2, 2, 2, 1)],
        ]
        cursor.fetchone.return_value = (
            json.dumps(
                {
                    "attempt_id": "attempt-1",
                    "status": "complete",
                    "loaded_rows": 2,
                    "processed_rows": 2,
                    "rejected_rows": 1,
                    "process_attempt_id": "process-1",
                }
            ),
        )
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with (
            patch("scripts.pipeline.process_history.connect_project", return_value=connection),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = process_history(1)
        self.assertEqual(result["completed_attempts"], 1)
        self.assertEqual(result["rejected_rows"], 1)
        self.assertEqual(
            sum(call.args[0].startswith("CALL ") for call in cursor.execute.call_args_list), 1
        )

    def test_changed_pending_state_stops_before_call(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            [("attempt-1", 2)],
            [("RECONCILED", 2, 2, 2, 2, 0)],
        ]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.pipeline.process_history.connect_project", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "state changed"):
                process_history(1)
        self.assertFalse(
            any(call.args[0].startswith("CALL ") for call in cursor.execute.call_args_list)
        )

    def test_batch_limit(self):
        with self.assertRaises(ValueError):
            process_history(201)


if __name__ == "__main__":
    unittest.main()
