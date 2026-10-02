"""Offline checks for the guarded Phase 3 view deployment and report."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.checks.phase3_quality import VIEW_NAMES, execute_quality, main, reviewed_sql, view_action


class Phase3QualityTest(unittest.TestCase):
    def test_preview_checks_reviewed_files_without_connecting(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase3_quality.py"]), \
             patch("scripts.checks.phase3_quality.connect_project",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertEqual([len(group) for group in reviewed_sql()], [3, 3, 1])

    def test_changed_sql_stops_before_connection(self):
        with patch("scripts.checks.phase3_quality.FILES",
                   (("phase3_health_views.sql", "wrong", 3),)), \
             patch("scripts.checks.phase3_quality.connect_project") as connect:
            with self.assertRaisesRegex(ValueError, "changed"):
                execute_quality()
        connect.assert_not_called()

    def test_partial_existing_view_stops_before_ddl(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [("V_BATCH_HEALTH", "different")]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.checks.phase3_quality.connect_project", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "partial or differ"):
                execute_quality()
        self.assertFalse(any(call.args[0].startswith("CREATE VIEW")
                             for call in cursor.execute.call_args_list))

    def test_runs_three_new_views_then_bounded_quality_reads(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(0,), (0,)]
        cursor.fetchall.side_effect = [
            [],
            [("PENDING_PROCESS", 177, 216361, 216361, 0, 0, 0)],
            [("seattle", 15, 0.1, 2.0, "start", "end")],
        ]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.checks.phase3_quality.connect_project", return_value=connection):
            report = execute_quality()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["views_created"], list(VIEW_NAMES))
        self.assertEqual(report["batch_anomaly_rows"], 0)
        sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("CREATE VIEW ") for item in sql), 3)
        self.assertEqual(sum(item.startswith("SELECT COUNT(*) FROM (") for item in sql), 2)
        self.assertFalse(any(item.startswith("DROP ") for item in sql))

    def test_exact_existing_views_are_reused_without_ddl(self):
        views = reviewed_sql()[0]
        self.assertEqual(view_action(list(zip(VIEW_NAMES, views)), views), "reuse")
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(0,), (0,)]
        cursor.fetchall.side_effect = [
            list(zip(VIEW_NAMES, views)),
            [("RECONCILED", 1, 15, 15, 15, 15, 0)],
            [("seattle", 15, 0.1, 2.0, "start", "end")],
        ]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.checks.phase3_quality.connect_project", return_value=connection):
            report = execute_quality()
        self.assertEqual(report["views_created"], [])
        self.assertEqual(report["views_reused"], list(VIEW_NAMES))
        self.assertFalse(any(call.args[0].startswith("CREATE VIEW")
                             for call in cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
