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
                                      get_features, request_with_retry, run_batch,
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
