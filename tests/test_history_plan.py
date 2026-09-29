"""Offline tests for the initial five-year origin-time plan."""

import unittest
import io
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from quakewatch.history_plan import history_windows, main, selected_history_window
from quakewatch.settings import EVENT_HORIZON_YEARS, SITES


class HistoryPlanTests(unittest.TestCase):
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

    def test_execute_without_window_is_rejected(self) -> None:
        with patch("sys.argv", ["history_plan", "--cutoff", "2026-09-29", "--execute"]):
            with patch("quakewatch.history_plan.run_batch") as extract:
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main()
        extract.assert_not_called()
