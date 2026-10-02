"""Local contract check for retryable transformation attempt records."""

import unittest
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "sql/phase2_process_attempt.sql").read_text()


class ProcessAttemptSqlContractTest(unittest.TestCase):
    def test_separate_process_and_source_attempt_ids(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT", SQL)
        self.assertIn("PROCESS_ATTEMPT_ID VARCHAR NOT NULL", SQL)
        self.assertIn("ATTEMPT_ID VARCHAR NOT NULL", SQL)

    def test_outcome_counts_and_failure_details_are_retained(self) -> None:
        for column in (
            "STARTED_AT TIMESTAMP_TZ NOT NULL", "FINISHED_AT TIMESTAMP_TZ NOT NULL",
            "STATUS VARCHAR NOT NULL", "STAGING_PARSER_VERSION VARCHAR NOT NULL",
            "LOADED_ROWS NUMBER(38, 0) NOT NULL",
            "PROCESSED_ROWS NUMBER(38, 0) NOT NULL",
            "REJECTED_ROWS NUMBER(38, 0) NOT NULL",
            "REVISION_ROWS_MERGED NUMBER(38, 0) NOT NULL",
            "ERROR_TYPE VARCHAR", "ERROR_MESSAGE VARCHAR",
        ):
            with self.subTest(column=column):
                self.assertIn(column, SQL)


if __name__ == "__main__":
    unittest.main()
