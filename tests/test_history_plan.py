"""Offline tests for the initial five-year origin-time plan."""

import unittest
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from quakewatch.history_plan import (captured_history_windows, history_windows, main,
                                     resume_capture, selected_history_window)
from quakewatch.settings import EVENT_HORIZON_YEARS, SITES


class HistoryPlanTests(unittest.TestCase):
    def test_resume_preview_is_bounded_and_makes_no_requests(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        with TemporaryDirectory() as folder:
            with patch("quakewatch.history_plan.run_batch") as extract:
                with redirect_stdout(io.StringIO()) as output:
                    selected = resume_capture(cutoff, Path(folder), 2, False)
            self.assertEqual(selected, [1, 2])
            extract.assert_not_called()
            self.assertIn("no USGS or Snowflake calls made", output.getvalue())
            with self.assertRaisesRegex(ValueError, "between 1 and 50"):
                resume_capture(cutoff, Path(folder), 51, False)
            self.assertEqual(len(resume_capture(cutoff, Path(folder), 50, False)), 50)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(resume_capture(cutoff, Path(folder), 3, False, 13),
                                 [13, 14, 15])
            with self.assertRaisesRegex(ValueError, "start-window must be between 1 and 180"):
                resume_capture(cutoff, Path(folder), 1, False, 181)

    def test_resume_stops_on_failed_manifest(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text(json.dumps({"status": "failed", "coverage_gaps": [{"window_id": "w0001"}]}),
                            encoding="utf-8")
            with patch("quakewatch.history_plan.run_batch", return_value=path) as extract:
                with redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "Window 1 did not reconcile"):
                        resume_capture(cutoff, Path(folder), 3, True)
            extract.assert_called_once()

    def test_resume_preview_skips_only_complete_local_captures(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for number, status in ((1, "complete"), (2, "failed"), (3, "complete")):
                site, start, end = selected_history_window(cutoff, number)
                attempt = root / str(number)
                attempt.mkdir()
                (attempt / "events.jsonl").write_text("", encoding="utf-8")
                (attempt / "manifest.json").write_text(json.dumps({
                    "status": status, "coverage_gaps": [], "site": {"name": SITES[site].name},
                    "requested_starttime": start.isoformat(), "requested_endtime": end.isoformat(),
                    "events_file": "events.jsonl",
                }), encoding="utf-8")
            self.assertEqual(set(captured_history_windows(cutoff, root)), {1, 3})
            with patch("sys.argv", ["history_plan", "--cutoff", "2026-09-29", "--output",
                                    str(root), "--resume-preview"]):
                with redirect_stdout(io.StringIO()) as output:
                    main()
            self.assertIn("Locally captured windows: 2 of 180", output.getvalue())
            self.assertIn("Next uncaptured: 2 seattle", output.getvalue())

    def test_three_sites_get_sixty_contiguous_windows_each(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        windows = history_windows(cutoff)
        self.assertEqual(len(windows), len(SITES) * EVENT_HORIZON_YEARS * 12)
        for site_key in SITES:
            site_windows = [(start, end) for site, start, end in windows if site == site_key]
            self.assertEqual(site_windows[0][0], datetime(2021, 9, 29, tzinfo=UTC))
            self.assertEqual(site_windows[0][1], datetime(2021, 10, 29, tzinfo=UTC))
            self.assertEqual(site_windows[-1][1], cutoff)
            self.assertTrue(all(start < end for start, end in site_windows))
            self.assertTrue(all(left[1] == right[0] for left, right in zip(site_windows, site_windows[1:])))

    def test_leap_day_cutoff_keeps_contiguous_boundaries(self) -> None:
        windows = history_windows(datetime(2024, 2, 29, tzinfo=UTC))
        seattle = [(start, end) for site, start, end in windows if site == "seattle"]
        self.assertEqual(seattle[0][0], datetime(2019, 2, 28, tzinfo=UTC))
        self.assertEqual(seattle[-1][1], datetime(2024, 2, 29, tzinfo=UTC))
        self.assertTrue(all(left[1] == right[0] for left, right in zip(seattle, seattle[1:])))

    def test_naive_cutoff_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            history_windows(datetime(2026, 9, 29))

    def test_selects_one_window_and_rejects_out_of_range(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        self.assertEqual(selected_history_window(cutoff, 1)[0], "seattle")
        self.assertEqual(selected_history_window(cutoff, 61)[0], "san-francisco")
        self.assertEqual(selected_history_window(cutoff, 180)[0], "anchorage")
        with self.assertRaisesRegex(ValueError, "between 1 and 180"):
            selected_history_window(cutoff, 0)
        with self.assertRaisesRegex(ValueError, "between 1 and 180"):
            selected_history_window(cutoff, 181)

    def test_preview_does_not_extract(self) -> None:
        with patch("sys.argv", ["history_plan", "--cutoff", "2026-09-29", "--window", "1"]):
            with patch("quakewatch.history_plan.run_batch") as extract:
                with redirect_stdout(io.StringIO()) as output:
                    main()
        extract.assert_not_called()
        self.assertIn("Preview only", output.getvalue())

    def test_execute_extracts_only_selected_window(self) -> None:
        args = ["history_plan", "--cutoff", "2026-09-29", "--window", "1", "--execute"]
        with patch("sys.argv", args):
            with patch("quakewatch.history_plan.run_batch", return_value=Path("manifest.json")) as extract:
                with redirect_stdout(io.StringIO()):
                    main()
        extract.assert_called_once_with(
            "seattle", datetime(2021, 9, 29, tzinfo=UTC),
            datetime(2021, 10, 29, tzinfo=UTC), Path("data/raw")
        )

    def test_execute_passes_week_source_option(self) -> None:
        args = ["history_plan", "--cutoff", "2026-09-29", "--window", "73",
                "--source-days", "7", "--execute"]
        with patch("sys.argv", args):
            with patch("quakewatch.history_plan.run_batch", return_value=Path("manifest.json")) as extract:
                with redirect_stdout(io.StringIO()):
                    main()
        self.assertEqual(extract.call_args.kwargs, {"source_days": 7})

    def test_execute_passes_child_resume_option(self) -> None:
        args = ["history_plan", "--cutoff", "2026-09-29", "--window", "73",
                "--source-days", "1", "--resume-children", "--execute"]
        with patch("sys.argv", args):
            with patch("quakewatch.history_plan.run_batch", return_value=Path("manifest.json")) as extract:
                with redirect_stdout(io.StringIO()):
                    main()
        self.assertEqual(extract.call_args.kwargs,
                         {"source_days": 1, "resume_children": True})

    def test_child_resume_requires_source_days(self) -> None:
        args = ["history_plan", "--cutoff", "2026-09-29", "--window", "73",
                "--resume-children", "--execute"]
        with patch("sys.argv", args):
            with patch("quakewatch.history_plan.run_batch") as extract:
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main()
        extract.assert_not_called()

    def test_execute_without_window_is_rejected(self) -> None:
        with patch("sys.argv", ["history_plan", "--cutoff", "2026-09-29", "--execute"]):
            with patch("quakewatch.history_plan.run_batch") as extract:
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main()
        extract.assert_not_called()
