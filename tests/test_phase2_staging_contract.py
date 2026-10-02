"""Guard the local Phase 2 staging DDL against accidental contract drift."""

import unittest
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "sql/phase2_staging_table.sql").read_text()


class StagingTableContractTest(unittest.TestCase):
    def test_one_observation_keeps_raw_lineage_and_parser_versions(self) -> None:
        for column in (
            "STAGE_FILE_NAME", "STAGE_FILE_ROW_NUMBER", "ATTEMPT_ID",
            "WINDOW_ID", "FETCHED_AT", "PAYLOAD_HASH",
            "RAW_PARSER_VERSION", "STAGING_PARSER_VERSION",
        ):
            with self.subTest(column=column):
                self.assertRegex(SQL, rf"(?m)^\s*{column}\s+")

    def test_typed_projection_keeps_rejects_in_same_grain(self) -> None:
        for column in (
            "SOURCE_EVENT_ID", "ORIGIN_TIME", "SOURCE_UPDATED_AT",
            "SOURCE_STATUS", "ASSOCIATED_IDS", "MAGNITUDE",
            "MAGNITUDE_TYPE", "PLACE", "LONGITUDE", "LATITUDE",
            "DEPTH_KM", "REJECT_REASON", "PROJECTED_AT",
        ):
            with self.subTest(column=column):
                self.assertRegex(SQL, rf"(?m)^\s*{column}\s+")
        self.assertRegex(SQL, r"CREATE TABLE IF NOT EXISTS QUAKEWATCH\.CURATED\.STG_EVENT_REVISION")
        self.assertNotRegex(SQL, r"(?im)^\s*(?:INSERT|MERGE|COPY|DELETE|DROP)\b")


if __name__ == "__main__":
    unittest.main()
