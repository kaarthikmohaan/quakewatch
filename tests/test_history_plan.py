"""Offline tests for the initial five-year origin-time plan."""

import unittest
from datetime import UTC, datetime

from quakewatch.history_plan import history_windows
from quakewatch.settings import EVENT_HORIZON_YEARS, SITES


class HistoryPlanTests(unittest.TestCase):
    def test_three_sites_get_five_contiguous_windows_each(self) -> None:
        cutoff = datetime(2026, 9, 29, tzinfo=UTC)
        windows = history_windows(cutoff)
        self.assertEqual(len(windows), len(SITES) * EVENT_HORIZON_YEARS)
        for site_key in SITES:
            site_windows = [(start, end) for site, start, end in windows if site == site_key]
            self.assertEqual(site_windows[0][0], datetime(2021, 9, 29, tzinfo=UTC))
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
