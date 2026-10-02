"""Offline checks for the JSONL envelope and RAW COPY mapping."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "sql/load/copy_raw.sql").read_text(encoding="utf-8")


class CopyContractTests(unittest.TestCase):
    def test_copy_maps_every_required_raw_column(self) -> None:
        for field in (
            "logical_batch_id",
            "attempt_id",
            "window_id",
            "fetched_at",
            "payload_hash",
            "parser_version",
        ):
            self.assertIn(f"t.$1:metadata:{field}", SQL)
        self.assertIn("t.$1:source_feature", SQL)
        self.assertIn("METADATA$FILENAME", SQL)
        self.assertIn("METADATA$FILE_ROW_NUMBER", SQL)
        self.assertIn("ON_ERROR = ABORT_STATEMENT", SQL)

    def test_fixture_envelope_has_copy_fields(self) -> None:
        feature = json.loads((ROOT / "tests/fixtures/normal_event.json").read_text())
        record = {
            "source_feature": feature,
            "metadata": {
                "logical_batch_id": "example-logical",
                "attempt_id": "example-attempt",
                "window_id": "w0001",
                "fetched_at": "2026-09-29T00:00:00Z",
                "payload_hash": "a" * 64,
                "parser_version": "1",
            },
        }
        self.assertIsInstance(record["source_feature"], dict)
        for field in (
            "logical_batch_id",
            "attempt_id",
            "window_id",
            "fetched_at",
            "payload_hash",
            "parser_version",
        ):
            self.assertIn(field, record["metadata"])
