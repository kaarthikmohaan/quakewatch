"""Offline check that the old-origin diagnostic only reads fixture tables."""

import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.old_origin_state import main


class OldOriginStateTest(unittest.TestCase):
    def test_reports_counts_audits_and_current_without_writes(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            [("fixture-old-origin-original-v1", "complete", 1)],
            [("qw-old-origin-001", 1.1, "2020-01-15")],
        ]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        output = io.StringIO()
        with patch("scripts.evidence.phase2.old_origin_state.connect_project",
                   return_value=connection), \
             patch("scripts.evidence.phase2.old_origin_state._counts",
                   return_value={"DIM_DATE": 3}), \
             contextlib.redirect_stdout(output):
            main()
        report = json.loads(output.getvalue())
        self.assertEqual(report["differences_from_original"], {})
        self.assertEqual(report["current"], [["qw-old-origin-001", 1.1, "2020-01-15"]])
        sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any(item.lstrip().upper().startswith(
            ("CALL", "INSERT", "UPDATE", "DELETE", "MERGE", "PUT", "COPY")) for item in sql))


if __name__ == "__main__":
    unittest.main()
