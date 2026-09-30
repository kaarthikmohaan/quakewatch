"""Offline checks for bounded USGS response handling."""

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from quakewatch.extract_batch import (ExtractionError, SourceDeadlineExceeded, fetch_window,
                                      get_features, initial_request_windows, request_with_retry, run_batch,
                                      source_deadline, source_params)
from quakewatch.settings import SITES
from quakewatch.settings import MAX_TARGET_RESULTS_PER_WINDOW


FIXTURES = Path(__file__).parent / "fixtures"


class GetFeaturesTests(unittest.TestCase):
    def test_unknown_source_property_is_preserved(self) -> None:
        feature = json.loads((FIXTURES / "additive_field_event.json").read_text(encoding="utf-8"))
        body = json.dumps({"type": "FeatureCollection", "features": [feature]})
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(int(request.url.params["limit"]), MAX_TARGET_RESULTS_PER_WINDOW)
            return httpx.Response(200, text=body)

        transport = httpx.MockTransport(respond)

        with httpx.Client(transport=transport) as client:
            features = get_features(client, {})

        self.assertEqual(features, [feature])

    def test_malformed_whole_response_fails(self) -> None:
        body = (FIXTURES / "malformed_response.txt").read_text(encoding="utf-8")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))

        with httpx.Client(transport=transport) as client:
            with self.assertRaisesRegex(ExtractionError, "USGS query returned malformed JSON"):
                get_features(client, {})


class FetchWindowTests(unittest.TestCase):
    def test_planned_week_slices_keep_month_and_audit_each_child(self) -> None:
        start = datetime(2022, 9, 29, tzinfo=timezone.utc)
        end = datetime(2022, 10, 29, tzinfo=timezone.utc)
        slices = initial_request_windows(start, end, 7)
        self.assertEqual(len(slices), 5)
        self.assertEqual(slices[0][0], start)
        self.assertEqual(slices[-1][1], end)
        self.assertTrue(all(left[1] == right[0] for left, right in zip(slices, slices[1:])))
        calls = []

        def fake_fetch(_client, _site, child_start, child_end, window_id):
            calls.append((child_start, child_end, window_id))
            audit = {"window_id": window_id, "status": "reconciled", "count_before": 1,
                     "returned_rows": 1, "count_after": 1}
            return [({"id": window_id}, window_id)], [audit]

        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.extract_batch.fetch_window", side_effect=fake_fetch):
                path = run_batch("san-francisco", start, end, Path(directory), source_days=7)
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["requested_starttime"], source_params(SITES["san-francisco"], start, end)["starttime"])
            self.assertEqual(manifest["initial_source_days"], 7)
            self.assertEqual([a["status"] for a in manifest["window_audit"]],
                             ["split"] + ["reconciled"] * 5)
            self.assertEqual(manifest["raw_rows_written"], 5)
            with (path.parent / "events.jsonl").open() as stream:
                self.assertEqual(sum(1 for _ in stream), 5)
        self.assertEqual([(a, b) for a, b, _ in calls], slices)

    def test_failed_week_child_keeps_prior_audit_and_no_file(self) -> None:
        start = datetime(2022, 9, 29, tzinfo=timezone.utc)
        end = datetime(2022, 10, 29, tzinfo=timezone.utc)
        good = ([], [{"window_id": "w0001.1", "status": "reconciled"}])
        gap = {"window_id": "w0001.2", "status": "unresolved", "reason": "timeout"}
        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.extract_batch.fetch_window", side_effect=[
                good, ExtractionError("timeout", [gap])]):
                with self.assertRaises(ExtractionError):
                    run_batch("san-francisco", start, end, Path(directory), source_days=7)
            manifest = json.loads(next(Path(directory).glob("*/manifest.json")).read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual([a["status"] for a in manifest["window_audit"]],
                             ["split", "reconciled", "unresolved"])
            self.assertEqual(manifest["coverage_gaps"], [gap])
            self.assertFalse(list(Path(directory).glob("*/events.jsonl")))

    def test_deadline_identifies_active_week_and_keeps_completed_week(self) -> None:
        start = datetime(2022, 9, 29, tzinfo=timezone.utc)
        end = datetime(2022, 10, 29, tzinfo=timezone.utc)
        good = ([], [{"window_id": "w0001.1", "status": "reconciled",
                      "count_before": 0, "returned_rows": 0, "count_after": 0}])
        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.extract_batch.fetch_window", side_effect=[
                good, SourceDeadlineExceeded("source window exceeded its wall-clock deadline")]):
                with self.assertRaises(SourceDeadlineExceeded):
                    run_batch("san-francisco", start, end, Path(directory), source_days=7)
            manifest = json.loads(next(Path(directory).glob("*/manifest.json")).read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual([a["status"] for a in manifest["window_audit"]],
                             ["split", "reconciled", "unresolved"])
            self.assertEqual(manifest["coverage_gaps"][0]["window_id"], "w0001.2")
            self.assertEqual(manifest["coverage_gaps"][0]["starttime"],
                             "2022-10-06T00:00:00.000Z")
            self.assertEqual(manifest["raw_rows_written"], 0)
            self.assertFalse(list(Path(directory).glob("*/events.jsonl")))

    def test_source_deadline_stops_next_retry_after_budget(self) -> None:
        client = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"count": 0})))
        with self.assertRaises(SourceDeadlineExceeded):
            with source_deadline(0.01):
                time.sleep(0.1)
                request_with_retry(client, "https://example.test/count", {})
        client.close()

    def test_deadline_failure_saves_full_window_gap(self) -> None:
        start = datetime(2023, 9, 29, tzinfo=timezone.utc)
        end = datetime(2023, 10, 29, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.extract_batch.fetch_window",
                       side_effect=SourceDeadlineExceeded("source window exceeded 180 seconds")):
                with self.assertRaises(SourceDeadlineExceeded):
                    run_batch("seattle", start, end, Path(directory))
            manifest_path = next(Path(directory).glob("*/manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["error_type"], "SourceDeadlineExceeded")
            self.assertEqual(manifest["raw_rows_written"], 0)
            self.assertEqual(len(manifest["coverage_gaps"]), 1)
            self.assertEqual(manifest["coverage_gaps"][0]["starttime"],
                             manifest["requested_starttime"])

    def test_keyboard_interrupt_saves_gap(self) -> None:
        start = datetime(2023, 9, 29, tzinfo=timezone.utc)
        end = datetime(2023, 10, 29, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.extract_batch.fetch_window", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    run_batch("seattle", start, end, Path(directory))
            manifest = json.loads(next(Path(directory).glob("*/manifest.json")).read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["error_type"], "KeyboardInterrupt")
            self.assertEqual(len(manifest["coverage_gaps"]), 1)

    def test_parent_count_timeout_splits_into_reconciled_children(self) -> None:
        start = datetime(2022, 8, 29, tzinfo=timezone.utc)
        end = datetime(2022, 9, 29, tzinfo=timezone.utc)
        parent = source_params(SITES["seattle"], start, end)
        parent_bounds = (parent["starttime"], parent["endtime"])
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            bounds = (request.url.params["starttime"], request.url.params["endtime"])
            requests.append((request.url.path, bounds))
            if request.url.path.endswith("/count"):
                if bounds == parent_bounds:
                    raise httpx.ReadTimeout("parent timed out")
                return httpx.Response(200, json={"count": 0})
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

        with patch("quakewatch.extract_batch.time.sleep"):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                rows, audits = fetch_window(client, SITES["seattle"], start, end, "timeout")
        self.assertEqual(rows, [])
        self.assertEqual([audit["status"] for audit in audits], ["split", "reconciled", "reconciled"])
        self.assertIn("timed out", audits[0]["reason"])
        self.assertFalse(any(path.endswith("/query") and bounds == parent_bounds
                             for path, bounds in requests))

    def test_repeated_child_timeout_remains_explicit_gap(self) -> None:
        start = datetime(2022, 8, 29, tzinfo=timezone.utc)
        end = datetime(2022, 9, 29, tzinfo=timezone.utc)
        transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(
            httpx.ReadTimeout("still timed out")))
        with patch("quakewatch.extract_batch.time.sleep"):
            with httpx.Client(transport=transport) as client:
                with self.assertRaises(ExtractionError) as caught:
                    fetch_window(client, SITES["seattle"], start, end, "timeout")
        self.assertEqual([audit["status"] for audit in caught.exception.window_audit],
                         ["split", "split", "split", "unresolved"])

    def test_incomplete_window_marks_batch_failed(self) -> None:
        case = json.loads((FIXTURES / "incomplete_window_case.json").read_text(encoding="utf-8"))
        feature = json.loads((FIXTURES / "normal_event.json").read_text(encoding="utf-8"))
        returned_features = [feature][: case["returned_features"]]
        start = datetime.fromisoformat(case["starttime"].replace("Z", "+00:00"))
        end = start + timedelta(microseconds=case["window_duration_microseconds"])
        count_calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal count_calls
            if request.url.path.endswith("/count"):
                count_calls += 1
                value = case["count_before"] if count_calls % 2 else case["count_after"]
                return httpx.Response(200, json={"count": value})
            if request.url.path.endswith("/query"):
                return httpx.Response(200, json={"type": "FeatureCollection", "features": returned_features})
            raise AssertionError(f"Unexpected request: {request.url}")

        client = httpx.Client(transport=httpx.MockTransport(respond))
        with tempfile.TemporaryDirectory() as directory:
            with patch("quakewatch.extract_batch.httpx.Client", return_value=client):
                with self.assertRaisesRegex(ExtractionError, "counts disagree"):
                    run_batch("seattle", start, end, Path(directory))

            manifests = list(Path(directory).glob("*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["error_type"], "ExtractionError")
            self.assertIn("w0001", manifest["error"])
            self.assertIn("counts disagree", manifest["error"])
            self.assertNotEqual(manifest["requested_starttime"], manifest["requested_endtime"])
            self.assertEqual(len(manifest["coverage_gaps"]), 1)
            gap = manifest["coverage_gaps"][0]
            self.assertTrue(gap["window_id"].startswith("w0001."))
            self.assertEqual(gap["status"], "unresolved")
            self.assertIn("counts disagree", gap["reason"])
            self.assertEqual(manifest["window_audit"][0]["status"], "split")
            self.assertEqual(manifest["window_audit"][-1], gap)
            self.assertFalse(list(Path(directory).glob("*/events.jsonl")))

    def test_over_limit_parent_is_split_before_feature_request(self) -> None:
        case = json.loads((FIXTURES / "over_limit_case.json").read_text(encoding="utf-8"))
        start = datetime.fromisoformat(case["starttime"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(case["endtime"].replace("Z", "+00:00"))
        parent_params = source_params(SITES["seattle"], start, end)
        parent_window = (parent_params["starttime"], parent_params["endtime"])
        query_windows: list[tuple[str, str]] = []

        def respond(request: httpx.Request) -> httpx.Response:
            window = (request.url.params["starttime"], request.url.params["endtime"])
            if request.url.path.endswith("/count"):
                count = case["parent_count"] if window == parent_window else case["child_count"]
                return httpx.Response(200, json={"count": count})
            if request.url.path.endswith("/query"):
                query_windows.append(window)
                return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
            raise AssertionError(f"Unexpected request: {request.url}")

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            rows, audits = fetch_window(client, SITES["seattle"], start, end, "over-limit")

        self.assertEqual(rows, [])
        self.assertEqual([audit["status"] for audit in audits], ["split", "reconciled", "reconciled"])
        self.assertIn("reached safe target 10000", audits[0]["reason"])
        self.assertEqual(len(query_windows), 2)
        self.assertNotIn(parent_window, query_windows)

    def test_target_count_splits_before_service_limit(self) -> None:
        start = datetime(2026, 9, 28, tzinfo=timezone.utc)
        end = start + timedelta(seconds=2)
        parent = source_params(SITES["seattle"], start, end)
        parent_bounds = (parent["starttime"], parent["endtime"])
        queried: list[tuple[str, str]] = []

        def respond(request: httpx.Request) -> httpx.Response:
            bounds = (request.url.params["starttime"], request.url.params["endtime"])
            if request.url.path.endswith("/count"):
                count = MAX_TARGET_RESULTS_PER_WINDOW if bounds == parent_bounds else 0
                return httpx.Response(200, json={"count": count})
            queried.append(bounds)
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            rows, audits = fetch_window(client, SITES["seattle"], start, end, "target")

        self.assertEqual(rows, [])
        self.assertEqual([audit["status"] for audit in audits], ["split", "reconciled", "reconciled"])
        self.assertNotIn(parent_bounds, queried)

    def test_unresolved_count_mismatch_fails(self) -> None:
        case = json.loads((FIXTURES / "count_mismatch_case.json").read_text(encoding="utf-8"))
        feature = json.loads((FIXTURES / case["feature_fixture"]).read_text(encoding="utf-8"))
        body = {"type": "FeatureCollection", "features": [feature]}
        count_calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal count_calls
            if request.url.path.endswith("/count"):
                count_calls += 1
                value = case["count_before"] if count_calls % 2 else case["count_after"]
                return httpx.Response(200, json={"count": value})
            return httpx.Response(200, json=body)

        start = datetime.fromtimestamp(feature["properties"]["time"] / 1000, tz=timezone.utc)
        end = start + timedelta(microseconds=case["window_duration_microseconds"])
        transport = httpx.MockTransport(respond)

        with httpx.Client(transport=transport) as client:
            with self.assertRaisesRegex(
                ExtractionError, r"counts disagree \(before=2, rows=1, after=2\)"
            ):
                fetch_window(client, SITES["seattle"], start, end, "mismatch")


if __name__ == "__main__":
    unittest.main()
