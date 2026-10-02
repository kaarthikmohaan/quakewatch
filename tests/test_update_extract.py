"""Offline update-sweep extraction and failure evidence."""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from quakewatch.extract_batch import ExtractionError, SourceDeadlineExceeded
from quakewatch.raw_load import validate_local_batch
from quakewatch.update_extract import initial_sweep_windows, run_update_sweep


class UpdateExtractTests(unittest.TestCase):
    def setUp(self):
        self.values = (
            datetime(1900, 1, 1, tzinfo=UTC),
            datetime(2026, 9, 30, tzinfo=UTC),
            datetime(2026, 9, 29, tzinfo=UTC),
            datetime(2026, 9, 30, tzinfo=UTC),
            86400,
        )

    def test_split_preserves_update_filter_and_old_deleted_records(self):
        requests = []

        def respond(request):
            params = dict(request.url.params)
            requests.append(params)
            self.assertEqual(params["updatedafter"], "2026-09-28T00:00:00.000Z")
            self.assertEqual(params["includedeleted"], "true")
            self.assertFalse(
                {"latitude", "longitude", "minmagnitude", "maxradiuskm"} & params.keys()
            )
            parent = params["starttime"].startswith("1900-") and params["endtime"].startswith(
                "2000-"
            )
            if request.url.path.endswith("/count"):
                return httpx.Response(200, json={"count": 10000 if parent else 1})
            self.assertFalse(parent)
            return httpx.Response(
                200,
                json={
                    "features": [
                        {"id": "old-event", "properties": {"status": "deleted", "time": -1000}}
                    ]
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(respond))
        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.update_extract.httpx.Client", return_value=client):
                path = run_update_sweep(
                    *self.values, Path(directory), years_per_window=100, recent_start_year=2026
                )
            manifest, count = validate_local_batch(path)
            self.assertEqual(count, 4)
            self.assertEqual(
                [a["status"] for a in manifest["window_audit"]],
                ["split", "split", "reconciled", "reconciled", "reconciled", "reconciled"],
            )
            self.assertFalse(manifest["watermark_advanced"])
            self.assertEqual(manifest["last_committed_watermark"], "2026-09-29T00:00:00.000Z")
            self.assertEqual(manifest["coverage_gaps"], [])
            self.assertIn("deleted", (path.parent / "events.jsonl").read_text())

    def test_failure_preserves_watermark_and_explicit_gap(self):
        gap = {"window_id": "w0001.a", "status": "unresolved", "reason": "counts disagree"}
        for error in (
            ExtractionError("counts disagree", [gap]),
            SourceDeadlineExceeded("deadline"),
        ):
            with (
                self.subTest(error=type(error).__name__),
                tempfile.TemporaryDirectory() as directory,
            ):
                with patch("quakewatch.update_extract.fetch_window", side_effect=error):
                    with self.assertRaises(type(error)):
                        run_update_sweep(*self.values, Path(directory))
                path = next(Path(directory).glob("*/manifest.json"))
                m = json.loads(path.read_text())
                self.assertEqual(m["status"], "failed")
                self.assertFalse(m["watermark_advanced"])
                self.assertEqual(m["last_committed_watermark"], "2026-09-29T00:00:00.000Z")
                self.assertTrue(m["coverage_gaps"])
                self.assertFalse((path.parent / "events.jsonl").exists())

    def test_planned_windows_are_contiguous_and_bounded(self):
        windows = initial_sweep_windows(
            datetime(1, 1, 1, tzinfo=UTC), datetime(2026, 9, 30, tzinfo=UTC), 50
        )
        self.assertEqual(len(windows), 46)
        self.assertEqual(windows[0][0], datetime(1, 1, 1, tzinfo=UTC))
        self.assertEqual(windows[-1][1], datetime(2026, 9, 30, tzinfo=UTC))
        self.assertTrue(all(a[1] == b[0] for a, b in zip(windows, windows[1:])))
        self.assertEqual(windows[39][1], datetime(2001, 1, 1, tzinfo=UTC))
        self.assertEqual(windows[40][1], datetime(2006, 1, 1, tzinfo=UTC))

    def test_monthly_recent_windows_are_contiguous_and_bounded(self):
        start = datetime(2022, 1, 1, tzinfo=UTC)
        cutoff = datetime(2024, 2, 15, tzinfo=UTC)
        windows = initial_sweep_windows(start, cutoff, 50, 2001, 5, 2023, 1)
        self.assertEqual(windows[0], (start, datetime(2023, 1, 1, tzinfo=UTC)))
        self.assertEqual(
            windows[1], (datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 2, 1, tzinfo=UTC))
        )
        self.assertEqual(len(windows), 15)
        self.assertEqual(windows[-1][1], cutoff)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(windows, windows[1:])))

    def test_monthly_recent_windows_reject_invalid_configuration(self):
        with self.assertRaisesRegex(ValueError, "monthly-start-year"):
            initial_sweep_windows(
                datetime(2022, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, tzinfo=UTC),
                50,
                2001,
                5,
                2000,
            )

    def test_one_daily_month_preserves_earlier_window_ids_and_coverage(self):
        start = datetime(1, 1, 1, tzinfo=UTC)
        cutoff = datetime(2026, 9, 30, tzinfo=UTC)
        monthly = initial_sweep_windows(start, cutoff, 50, 2001, 1, 2023, 1)
        daily = initial_sweep_windows(start, cutoff, 50, 2001, 1, 2023, 1, "2023-10")
        self.assertEqual(daily[:71], monthly[:71])
        self.assertEqual(
            daily[71], (datetime(2023, 10, 1, tzinfo=UTC), datetime(2023, 10, 2, tzinfo=UTC))
        )
        self.assertEqual(daily[101][1], datetime(2023, 11, 1, tzinfo=UTC))
        self.assertEqual(daily[-1][1], cutoff)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(daily, daily[1:])))

    def test_daily_month_must_be_bounded_and_in_monthly_range(self):
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)
        for daily_month in ("2023-13", "2022-12", "2024-01"):
            with self.subTest(daily_month=daily_month), self.assertRaises(ValueError):
                initial_sweep_windows(start, end, 50, 2001, 1, 2023, 1, daily_month)

    def test_deadline_after_first_child_preserves_precise_gap(self):
        values = (
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            86400,
        )
        first = (
            [({"id": "old"}, "w0001.1")],
            [
                {
                    "window_id": "w0001.1",
                    "starttime": "2024-01-01T00:00:00.000Z",
                    "endtime": "2025-01-01T00:00:00.000Z",
                    "status": "reconciled",
                    "count_before": 1,
                    "returned_rows": 1,
                    "count_after": 1,
                }
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "quakewatch.update_extract.fetch_window",
                side_effect=[first, SourceDeadlineExceeded("deadline")],
            ):
                with self.assertRaises(SourceDeadlineExceeded):
                    run_update_sweep(
                        *values, Path(directory), years_per_window=1, recent_years_per_window=1
                    )
            m = json.loads(next(Path(directory).glob("*/manifest.json")).read_text())
            self.assertEqual(
                [a["status"] for a in m["window_audit"]], ["split", "reconciled", "unresolved"]
            )
            self.assertEqual(m["coverage_gaps"][0]["starttime"], "2025-01-01T00:00:00.000Z")
            self.assertFalse(m["watermark_advanced"])
            self.assertFalse(list(Path(directory).glob("*/events.jsonl")))

    def test_retry_reuses_validated_child_from_same_frozen_sweep(self):
        values = (
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            86400,
        )

        def child(index):
            year = 2023 + index
            window_id = f"w0001.{index}"
            return (
                [({"id": f"event-{index}"}, window_id)],
                [
                    {
                        "window_id": window_id,
                        "starttime": f"{year}-01-01T00:00:00.000Z",
                        "endtime": f"{year + 1}-01-01T00:00:00.000Z",
                        "status": "reconciled",
                        "count_before": 1,
                        "returned_rows": 1,
                        "count_after": 1,
                    }
                ],
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "quakewatch.update_extract.fetch_window",
                side_effect=[child(1), SourceDeadlineExceeded("deadline")],
            ):
                with self.assertRaises(SourceDeadlineExceeded):
                    run_update_sweep(
                        *values,
                        root,
                        years_per_window=1,
                        recent_years_per_window=1,
                        resume_children=True,
                    )
            failed_path = next(root.glob("*/manifest.json"))
            self.assertFalse((failed_path.parent / "events.jsonl").exists())
            with patch("quakewatch.update_extract.fetch_window", return_value=child(2)) as fetch:
                complete_path = run_update_sweep(
                    *values,
                    root,
                    years_per_window=1,
                    recent_years_per_window=1,
                    resume_children=True,
                )
            self.assertEqual(fetch.call_count, 1)
            manifest, count = validate_local_batch(complete_path)
            self.assertEqual(count, 2)
            self.assertEqual(manifest["reused_child_windows"], ["w0001.1"])
            self.assertEqual(manifest["source_rows_reused"], 1)
            self.assertEqual(manifest["source_rows_fetched_this_attempt"], 1)
            self.assertFalse(manifest["watermark_advanced"])

    def test_tampered_checkpoint_is_refetched(self):
        values = (
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, tzinfo=UTC),
            86400,
        )
        child = (
            [({"id": "event"}, "w0001")],
            [
                {
                    "window_id": "w0001",
                    "starttime": "2024-01-01T00:00:00.000Z",
                    "endtime": "2025-01-01T00:00:00.000Z",
                    "status": "reconciled",
                    "count_before": 1,
                    "returned_rows": 1,
                    "count_after": 1,
                }
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("quakewatch.update_extract.fetch_window", return_value=child):
                first = run_update_sweep(*values, root, years_per_window=1, resume_children=True)
            checkpoint = first.parent / "children" / "w0001.json"
            wrapper = json.loads(checkpoint.read_text())
            wrapper["payload"]["features"][0][0]["id"] = "tampered"
            checkpoint.write_text(json.dumps(wrapper))
            with patch("quakewatch.update_extract.fetch_window", return_value=child) as fetch:
                second = run_update_sweep(*values, root, years_per_window=1, resume_children=True)
            self.assertEqual(fetch.call_count, 1)
            manifest, count = validate_local_batch(second)
            self.assertEqual(count, 1)
            self.assertEqual(manifest["reused_child_windows"], [])

    def test_different_sweep_start_does_not_reuse_checkpoint(self):
        values = (
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, tzinfo=UTC),
            86400,
        )
        child = (
            [],
            [
                {
                    "window_id": "w0001",
                    "starttime": "2024-01-01T00:00:00.000Z",
                    "endtime": "2025-01-01T00:00:00.000Z",
                    "status": "reconciled",
                    "count_before": 0,
                    "returned_rows": 0,
                    "count_after": 0,
                }
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("quakewatch.update_extract.fetch_window", return_value=child):
                run_update_sweep(*values, root, resume_children=True)
            later = (*values[:3], datetime(2025, 1, 2, tzinfo=UTC), values[4])
            with patch("quakewatch.update_extract.fetch_window", return_value=child) as fetch:
                path = run_update_sweep(*later, root, resume_children=True)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(json.loads(path.read_text())["reused_child_windows"], [])
