"""Offline checks for the guarded old-origin fixture RAW loader."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.phase2_old_origin_raw_load import (
    REPLAY_COUNTS, SEQUENCE, _guard_before, execute_load, local_plans, main,
)
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE


class OldOriginRawLoadTest(unittest.TestCase):
    def test_preview_only_two_isolated_plans_without_connecting(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase2_old_origin_raw_load.py"]), \
             patch("scripts.evidence.phase2.phase2_old_origin_raw_load.connect_project",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertEqual([plan["attempt_id"] for plan in local_plans(SEQUENCE)],
                         [item[0] for item in SEQUENCE])
        for plan in local_plans(SEQUENCE):
            self.assertIn(TEST_DATABASE + ".RAW.RAW_EVENT_RECORDS", plan["copy_sql"])
            self.assertEqual(plan["manifest"]["fixture_only"], True)

    def test_changed_baseline_stops_before_put(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaisesRegex(RuntimeError, "baseline differs"):
            _guard_before(cursor, local_plans(SEQUENCE))
        self.assertEqual(cursor.execute.call_count, 1)

    def test_curated_state_must_match_stale_replay(self):
        cursor = MagicMock()
        prior = sorted((name, 1) for name in (
            "fixture-original-v1", "fixture-update-v1", "fixture-deletion-v1",
            "fixture-stale-replay-v1"))
        cursor.fetchall.return_value = prior
        with patch("scripts.evidence.phase2.phase2_old_origin_raw_load._counts",
                   return_value={**REPLAY_COUNTS, "FACT_EVENT_REVISION": 4}):
            with self.assertRaisesRegex(RuntimeError, "measured stale-replay state"):
                _guard_before(cursor, local_plans(SEQUENCE))
        self.assertFalse(any(call.args[0].startswith("PUT ")
                             for call in cursor.execute.call_args_list))

    def test_two_put_copy_calls_after_preflight(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (1,)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        events = []
        def result_dicts(_cursor):
            sql = cursor.execute.call_args.args[0]
            return ([{"status": "UPLOADED"}] if sql.startswith("PUT ")
                    else [{"status": "LOADED", "rows_loaded": 1}])
        with patch("scripts.evidence.phase2.phase2_old_origin_raw_load.connect_project", return_value=connection), \
             patch("scripts.evidence.phase2.phase2_old_origin_raw_load._guard_before",
                   side_effect=lambda *_: events.append("before")), \
             patch("scripts.evidence.phase2.phase2_old_origin_raw_load._guard_after",
                   side_effect=lambda *_: events.append("after")), \
             patch("scripts.evidence.phase2.phase2_old_origin_raw_load._result_dicts", side_effect=result_dicts), \
             patch("scripts.evidence.phase2.phase2_old_origin_raw_load._append_receipt",
                   side_effect=lambda *_: events.append("receipt")):
            results = execute_load()
        self.assertEqual(events, ["before", "receipt", "receipt", "after"])
        self.assertEqual([item["loaded_rows"] for item in results], [1, 1])
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sum(item.startswith("PUT ") for item in statements), 2)
        self.assertEqual(sum("COPY INTO " in item for item in statements), 2)


if __name__ == "__main__":
    unittest.main()
