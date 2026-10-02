"""Local contract checks for revision fact grain and current-view ordering."""

import unittest
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "sql/phase2_revision_current.sql").read_text()


class RevisionSqlContractTest(unittest.TestCase):
    def test_fact_contains_full_revision_key_and_source_clocks(self) -> None:
        self.assertIn("QUAKEWATCH.CURATED.FACT_EVENT_REVISION", SQL)
        for column in (
            "CANONICAL_EVENT_ID", "SOURCE_UPDATED_AT", "PAYLOAD_HASH",
            "SOURCE_EVENT_ID", "ASSOCIATED_IDS", "ORIGIN_TIME",
            "FETCHED_AT", "CURATED_AT", "SOURCE_STATUS",
            "STAGE_FILE_NAME", "STAGE_FILE_ROW_NUMBER",
        ):
            with self.subTest(column=column):
                self.assertRegex(SQL, rf"(?m)^\s*{column}\s+")

    def test_current_view_ranks_before_filtering_tombstones(self) -> None:
        view = SQL.split("CREATE OR REPLACE VIEW", 1)[1]
        self.assertRegex(view, r"PARTITION BY CANONICAL_EVENT_ID")
        self.assertRegex(
            view,
            r"ORDER BY SOURCE_UPDATED_AT DESC, FETCHED_AT DESC, PAYLOAD_HASH DESC",
        )
        self.assertRegex(
            view,
            r"FROM RANKED_REVISIONS\s+WHERE REVISION_RANK = 1 AND SOURCE_STATUS <> 'deleted'",
        )
        self.assertNotRegex(view.split("FROM RANKED_REVISIONS", 1)[0], r"\bWHERE\b")


if __name__ == "__main__":
    unittest.main()
