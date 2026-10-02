"""Offline one-attempt projection checks before Snowpark writes."""

import copy
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.process_batch import RawObservation, project_raw_attempt

FIXTURES = Path(__file__).parent / "fixtures"


def raw_row(name: str, row_number: int) -> RawObservation:
    payload = json.loads((FIXTURES / name).read_text())
    return RawObservation(
        attempt_id="attempt-1",
        window_id="w0001",
        stage_file_name="attempt-1/events.jsonl",
        stage_file_row_number=row_number,
        fetched_at=datetime(2026, 9, 30, tzinfo=UTC),
        payload_hash="a" * 64,
        raw_parser_version="1",
        payload=payload,
    )


class BatchProjectionTest(unittest.TestCase):
    def test_valid_and_rejected_rows_are_both_counted_and_traceable(self) -> None:
        valid = raw_row("normal_event.json", 1)
        invalid_payload = copy.deepcopy(valid.payload)
        invalid_payload["id"] = ""
        invalid = replace(valid, stage_file_row_number=2, payload=invalid_payload)
        result = project_raw_attempt([valid, invalid], "attempt-1", 2)
        self.assertEqual((result.loaded_rows, result.processed_rows, result.rejected_rows), (2, 2, 1))
        self.assertEqual(result.observations[1].raw.source_key, invalid.source_key)
        self.assertEqual(result.observations[1].fields["reject_reason"], "invalid_source_event_id")

    def test_receipt_count_mismatch_fails_before_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            project_raw_attempt([raw_row("normal_event.json", 1)], "attempt-1", 2)

    def test_other_attempt_and_duplicate_file_row_fail(self) -> None:
        row = raw_row("normal_event.json", 1)
        with self.assertRaisesRegex(ValueError, "different attempt"):
            project_raw_attempt([replace(row, attempt_id="attempt-2")], "attempt-1", 1)
        with self.assertRaisesRegex(ValueError, "duplicate RAW"):
            project_raw_attempt([row, row], "attempt-1", 2)

    def test_empty_complete_attempt_is_valid(self) -> None:
        result = project_raw_attempt([], "attempt-1", 0)
        self.assertEqual((result.processed_rows, result.rejected_rows), (0, 0))


if __name__ == "__main__":
    unittest.main()
