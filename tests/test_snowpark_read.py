"""Mock Snowpark reads without connecting to a warehouse."""

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.snowpark_read import read_and_project_attempt

FEATURE = json.loads((Path(__file__).parent / "fixtures/normal_event.json").read_text())


class FakeRow:
    def __init__(self, values: dict):
        self.values = values

    def as_dict(self) -> dict:
        return self.values


class FakeFrame:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def collect(self) -> list[FakeRow]:
        return [FakeRow(row) for row in self.rows]


class FakeSession:
    def __init__(self, receipt: list[dict], raw: list[dict]):
        self.receipt = receipt
        self.raw = raw
        self.calls = []

    def sql(self, query: str, params: list[str]) -> FakeFrame:
        self.calls.append((query, params))
        return FakeFrame(self.receipt if "BATCH_ATTEMPT" in query else self.raw)


def receipt(**changes: object) -> dict:
    row = dict(
        ATTEMPT_ID="attempt-1",
        EXTRACT_STATUS="complete",
        LOAD_STATUS="complete",
        COVERAGE_GAPS="[]",
        SOURCE_ROWS_RETURNED=1,
        RAW_ROWS_WRITTEN=1,
        LOADED_ROWS=1,
    )
    return {**row, **changes}


def raw(**changes: object) -> dict:
    row = dict(
        ATTEMPT_ID="attempt-1",
        WINDOW_ID="w0001",
        STAGE_FILE_NAME="attempt-1/events.jsonl",
        STAGE_FILE_ROW_NUMBER=1,
        FETCHED_AT=datetime(2026, 9, 30, tzinfo=UTC),
        PAYLOAD_HASH="a" * 64,
        PARSER_VERSION="1",
        PAYLOAD=json.dumps(FEATURE),
    )
    return {**row, **changes}


class SnowparkReadTest(unittest.TestCase):
    def test_complete_attempt_reads_only_bound_id_and_projects(self) -> None:
        session = FakeSession([receipt()], [raw()])
        projected = read_and_project_attempt(session, "attempt-1")
        self.assertEqual((projected.loaded_rows, projected.rejected_rows), (1, 0))
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(all(params == ["attempt-1"] for _, params in session.calls))
        self.assertTrue(all("WHERE ATTEMPT_ID = ?" in sql for sql, _ in session.calls))

    def test_missing_or_failed_receipt_stops_before_raw_read(self) -> None:
        for records in (
            [],
            [receipt(LOAD_STATUS="failed")],
            [receipt(COVERAGE_GAPS='[{"start":"unknown"}]')],
        ):
            with self.subTest(records=records):
                session = FakeSession(records, [raw()])
                with self.assertRaises(ValueError):
                    read_and_project_attempt(session, "attempt-1")
                self.assertEqual(len(session.calls), 1)

    def test_receipt_and_raw_count_mismatches_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "receipt counts"):
            read_and_project_attempt(FakeSession([receipt(LOADED_ROWS=2)], [raw()]), "attempt-1")
        with self.assertRaisesRegex(ValueError, "RAW row count"):
            read_and_project_attempt(FakeSession([receipt()], []), "attempt-1")

    def test_rejected_projection_keeps_raw_file_row(self) -> None:
        invalid = {**FEATURE, "id": ""}
        result = read_and_project_attempt(
            FakeSession([receipt()], [raw(PAYLOAD=json.dumps(invalid))]), "attempt-1"
        )
        self.assertEqual(result.rejected_rows, 1)
        self.assertEqual(result.observations[0].raw.stage_file_row_number, 1)


if __name__ == "__main__":
    unittest.main()
