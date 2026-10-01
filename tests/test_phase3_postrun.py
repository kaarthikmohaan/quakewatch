"""Post-run reporting remains read-only and checks reject reconciliation."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.phase3_postrun import main, postrun
from scripts.phase3_quality import VIEW_NAMES, reviewed_sql


class Phase3PostrunTest(unittest.TestCase):
    def test_preview_is_offline(self):
        with patch("sys.argv", ["phase3_postrun.py"]), \
             patch("scripts.phase3_postrun.connect_project",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(io.StringIO()):
            main()

    def test_full_report_passes_with_reconciled_rejects(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            list(zip(VIEW_NAMES, reviewed_sql()[0])),
            [("RECONCILED", 178, 216376, 216376, 216376, 216376, 485)],
            [("invalid_geometry", 485)],
        ]
        cursor.fetchone.side_effect = [(0,), (0,), (0,), (0,)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.phase3_postrun.connect_project", return_value=connection):
            report = postrun()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["reject_reasons"], [("invalid_geometry", 485)])
        self.assertFalse(any(call.args[0].startswith(("CREATE ", "DELETE ", "DROP "))
                             for call in cursor.execute.call_args_list))

    def test_reject_count_disagreement_is_review(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            list(zip(VIEW_NAMES, reviewed_sql()[0])),
            [("RECONCILED", 1, 10, 10, 10, 10, 2)],
            [("invalid_geometry", 1)],
        ]
        cursor.fetchone.side_effect = [(0,), (0,), (0,), (0,)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.phase3_postrun.connect_project", return_value=connection):
            self.assertEqual(postrun()["status"], "review")


if __name__ == "__main__":
    unittest.main()
