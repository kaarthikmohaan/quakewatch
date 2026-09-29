"""Offline reconciliation tests for the RAW loader."""

import json
import tempfile
import unittest
from pathlib import Path

from quakewatch.raw_load import LoadReconciliationError, reconcile_loaded_rows, validate_local_batch


class RawLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = {
            "status": "complete", "coverage_gaps": [], "events_file": "events.jsonl",
            "logical_batch_id": "logical", "attempt_id": "attempt",
            "fetched_at": "2026-09-29T00:00:00Z",
            "source_rows_returned": 1, "raw_rows_written": 1,
        }
        self.record = {
            "source_feature": {"id": "example"},
            "metadata": {
                "logical_batch_id": "logical", "attempt_id": "attempt",
                "fetched_at": "2026-09-29T00:00:00Z", "window_id": "w0001",
                "payload_hash": "a" * 64, "parser_version": "1",
            },
        }
        self.write_batch()

    def write_batch(self) -> None:
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.root / "events.jsonl").write_text(json.dumps(self.record) + "\n", encoding="utf-8")

    def test_matching_attempt_and_load_counts_pass(self) -> None:
        manifest, count = validate_local_batch(self.root / "manifest.json")
        self.assertEqual(manifest["attempt_id"], "attempt")
        self.assertEqual(count, 1)
        reconcile_loaded_rows(count, 1, 1)

    def test_unresolved_gap_blocks_load(self) -> None:
        self.manifest["coverage_gaps"] = [{"window_id": "w0001"}]
        self.write_batch()
        with self.assertRaisesRegex(LoadReconciliationError, "coverage gaps"):
            validate_local_batch(self.root / "manifest.json")

    def test_row_from_another_attempt_blocks_load(self) -> None:
        self.record["metadata"]["attempt_id"] = "other"
        self.write_batch()
        with self.assertRaisesRegex(LoadReconciliationError, "invalid events row 1"):
            validate_local_batch(self.root / "manifest.json")

    def test_missing_row_blocks_load(self) -> None:
        (self.root / "events.jsonl").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(LoadReconciliationError, "row counts disagree"):
            validate_local_batch(self.root / "manifest.json")

    def test_copy_or_raw_count_mismatch_blocks_success(self) -> None:
        with self.assertRaisesRegex(LoadReconciliationError, "copied=0"):
            reconcile_loaded_rows(1, 0, 1)
        with self.assertRaisesRegex(LoadReconciliationError, "raw=0"):
            reconcile_loaded_rows(1, 1, 0)
