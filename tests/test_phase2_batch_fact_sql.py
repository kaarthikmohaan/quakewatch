"""Local grain and metric contract for the Phase 2 batch fact."""

import unittest
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "sql/setup/08_batch_fact.sql").read_text()


class BatchFactSqlContractTest(unittest.TestCase):
    def test_one_attempt_grain_and_separate_counts(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.FACT_BATCH_RUN", SQL)
        for column in (
            "ATTEMPT_ID VARCHAR NOT NULL", "LOGICAL_BATCH_ID VARCHAR NOT NULL",
            "SOURCE_ROWS_RETURNED NUMBER", "RAW_ROWS_WRITTEN NUMBER",
            "LOADED_ROWS NUMBER", "PROCESSED_ROWS NUMBER", "REJECTED_ROWS NUMBER",
        ):
            with self.subTest(column=column):
                self.assertIn(column, SQL)

    def test_gaps_latency_and_processing_status_are_visible(self) -> None:
        for column in (
            "FETCHED_AT TIMESTAMP_TZ", "CURATED_AT TIMESTAMP_TZ",
            "FETCH_TO_CURATED_SECONDS NUMBER", "EXTRACT_STATUS VARCHAR",
            "LOAD_STATUS VARCHAR", "PROCESS_STATUS VARCHAR",
            "LAST_PROCESS_ATTEMPT_ID VARCHAR", "COVERAGE_GAPS VARIANT",
            "RECONCILIATION_OK BOOLEAN",
        ):
            with self.subTest(column=column):
                self.assertIn(column, SQL)


if __name__ == "__main__":
    unittest.main()
