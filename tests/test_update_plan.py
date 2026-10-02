"""Offline contract checks for update-sweep planning."""

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

from quakewatch.update_plan import main, plan_update_sweep


class UpdatePlanTests(unittest.TestCase):
    def setUp(self):
        self.args = dict(
            catalog_start=datetime(1900, 1, 1, tzinfo=UTC),
            cutoff=datetime(2026, 9, 30, tzinfo=UTC),
            last_watermark=datetime(2026, 9, 29, tzinfo=UTC),
            sweep_started_at=datetime(2026, 9, 30, tzinfo=UTC),
            overlap_seconds=86400,
        )

    def test_old_events_and_moved_events_are_not_filtered_out(self):
        plan = plan_update_sweep(**self.args)
        self.assertEqual(
            plan["query_parameters"],
            {
                "format": "geojson",
                "starttime": "1900-01-01T00:00:00.000Z",
                "endtime": "2026-09-30T00:00:00.000Z",
                "updatedafter": "2026-09-28T00:00:00.000Z",
                "includedeleted": "true",
                "orderby": "time-asc",
            },
        )
        self.assertFalse(plan["watermark_advanced"])
        self.assertEqual(plan["last_committed_watermark"], "2026-09-29T00:00:00.000Z")
        self.assertTrue(plan["count_sizing_pending"])

    def test_normalizes_timezones(self):
        self.args["sweep_started_at"] = datetime(
            2026, 9, 30, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )
        self.assertEqual(
            plan_update_sweep(**self.args)["sweep_started_at"], "2026-09-30T00:00:00.000Z"
        )

    def test_rejects_invalid_temporal_bounds_and_overlap(self):
        for changes in (
            {"overlap_seconds": 0},
            {"overlap_seconds": -1},
            {"overlap_seconds": True},
            {"catalog_start": self.args["cutoff"]},
            {"cutoff": self.args["sweep_started_at"] + timedelta(days=1)},
            {"last_watermark": self.args["sweep_started_at"] + timedelta(days=1)},
            {"cutoff": datetime(2026, 9, 30)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan_update_sweep(**{**self.args, **changes})

    def test_cli_preview_has_no_network_or_state_write(self):
        argv = [
            "update_plan",
            "--catalog-start",
            "1900-01-01",
            "--cutoff",
            "2026-09-30",
            "--last-watermark",
            "2026-09-29",
            "--sweep-started-at",
            "2026-09-30",
            "--overlap-seconds",
            "86400",
        ]
        with (
            patch("sys.argv", argv),
            patch("socket.socket") as network,
            patch("builtins.open") as files,
            redirect_stdout(io.StringIO()) as output,
        ):
            main()
        network.assert_not_called()
        files.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["status"], "preview")
