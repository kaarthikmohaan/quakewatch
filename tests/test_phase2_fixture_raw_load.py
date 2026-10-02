"""Offline checks for the isolated four-attempt RAW loader."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE
from scripts.evidence.phase2.phase2_fixture_raw_load import (
    _append_receipt, _guard_empty, execute_load, local_plans, main,
)


class FixtureRawLoadTest(unittest.TestCase):
    def test_preview_validates_four_local_plans_without_connecting(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase2_fixture_raw_load.py"]), \
             patch("scripts.evidence.phase2.phase2_fixture_raw_load.connect_project",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        plans = local_plans()
        self.assertEqual(len(plans), 4)
        self.assertIn("no Snowflake connection", output.getvalue())
        for plan in plans:
            self.assertIn(TEST_DATABASE + ".RAW.RAW_EVENT_RECORDS", plan["copy_sql"])
            self.assertNotIn("COPY INTO QUAKEWATCH.RAW.", plan["copy_sql"])
            self.assertEqual(plan["manifest"]["fixture_only"], True)

    def test_missing_or_changed_local_fixture_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.evidence.phase2.phase2_fixture_raw_load.ROOT", Path(directory)):
                with self.assertRaises(FileNotFoundError):
                    local_plans()

    def test_nonempty_raw_or_stage_stops_before_put(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        with self.assertRaisesRegex(RuntimeError, "not empty"):
            _guard_empty(cursor, local_plans())
        self.assertEqual(cursor.execute.call_count, 1)

    def test_receipt_insert_targets_only_fixture_database(self):
        cursor = MagicMock()
        plan = local_plans()[0]
        _append_receipt(cursor, plan, "complete", 1, [{"status": "LOADED"}])
        sql, values = cursor.execute.call_args.args
        self.assertIn(f"INSERT INTO {TEST_DATABASE}.RAW.BATCH_ATTEMPT", sql)
        self.assertNotIn("INSERT INTO QUAKEWATCH.RAW.BATCH_ATTEMPT", sql)
        self.assertEqual(values[0], plan["attempt_id"])
        self.assertEqual(values[11], "complete")
        self.assertEqual(values[14], 1)

    def test_execute_load_checks_empty_then_loads_four(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (1,)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        def result_dicts(_cursor):
            command = cursor.execute.call_args.args[0]
            return ([{"status": "UPLOADED"}] if command.startswith("PUT ")
                    else [{"status": "LOADED", "rows_loaded": 1}])
        with patch("scripts.evidence.phase2.phase2_fixture_raw_load.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.phase2_fixture_raw_load._guard_empty",
                   side_effect=lambda *_: events.append("guard")), \
             patch("scripts.evidence.phase2.phase2_fixture_raw_load._result_dicts", side_effect=result_dicts), \
             patch("scripts.evidence.phase2.phase2_fixture_raw_load._append_receipt",
                   side_effect=lambda *_: events.append("receipt")):
            results = execute_load()
        self.assertEqual(events, ["guard"] + ["receipt"] * 4)
        self.assertEqual([item["loaded_rows"] for item in results], [1] * 4)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("PUT ") for item in statements), 4)
        self.assertEqual(sum(item.startswith("COPY INTO ") or item.startswith("-- Phase 1")
                             for item in statements), 4)


if __name__ == "__main__":
    unittest.main()
