"""Keep the sample and acceptance target fixed before live measurement."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.checks.latency_metrics import TARGET_P95_SECONDS, main, measure, reviewed_statements


class Phase3MetricsTest(unittest.TestCase):
    def test_preview_is_offline_and_target_is_fixed(self):
        with (
            patch("sys.argv", ["phase3_metrics.py"]),
            patch(
                "scripts.checks.latency_metrics.connect_project",
                side_effect=AssertionError("connected"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            main()
        self.assertEqual(TARGET_P95_SECONDS, 86_400)
        statements = reviewed_statements()
        self.assertEqual(len(statements), 2)
        self.assertIn("2021-09-29T00:00:00Z", statements[0])
        self.assertIn("2026-09-29T00:00:00Z", statements[0])
        self.assertIn("PERCENTILE_CONT(0.95)", statements[0])

    def test_read_only_measurement_reports_sample_and_query_ids(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            (178, "start", "end", "first", "last", 10, 100, 500, 900),
            ("fetch", 42, "source", 84),
        ]
        cursor.sfqid = "query-id"
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.checks.latency_metrics.connect_project", return_value=connection):
            report = measure()
        self.assertTrue(report["target_met"])
        self.assertEqual(report["sample_attempts"], 178)
        self.assertEqual(report["query_ids"], ["query-id", "query-id"])
        self.assertFalse(
            any(
                call.args[0].startswith(("CREATE ", "DELETE ", "DROP "))
                for call in cursor.execute.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
