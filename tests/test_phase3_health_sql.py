"""Keep Phase 3 health views aligned with actual batch-count semantics."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "sql"
VIEWS = (ROOT / "phase3_health_views.sql").read_text()
CHECKS = (ROOT / "phase3_reconciliation.sql").read_text()


class Phase3HealthSqlTest(unittest.TestCase):
    def test_views_cover_receipts_processing_rejects_and_windows(self):
        self.assertEqual(VIEWS.count("CREATE VIEW"), 3)
        for name in ("V_BATCH_HEALTH", "V_RECEIPT_WINDOW_AUDIT", "V_EVENT_REJECTS"):
            self.assertIn(name, VIEWS)
        self.assertIn("QUAKEWATCH.RAW.BATCH_ATTEMPT", VIEWS)
        self.assertIn("QUAKEWATCH.RAW.RAW_EVENT_RECORDS", VIEWS)
        self.assertIn("QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT", VIEWS)
        self.assertIn("LATERAL FLATTEN(INPUT => a.WINDOW_AUDIT)", VIEWS)
        self.assertIn("REJECT_REASON IS NOT NULL", VIEWS)

    def test_processed_count_includes_rejected_rows(self):
        # BatchProjection.processed_rows counts all projected rows, including rejects.
        self.assertIn("p.PROCESSED_ROWS <> p.LOADED_ROWS", VIEWS)
        self.assertIn("p.REJECTED_ROWS > p.PROCESSED_ROWS", VIEWS)
        self.assertNotIn("p.PROCESSED_ROWS + p.REJECTED_ROWS", VIEWS)
        self.assertIn("COALESCE(s.REJECT_ROWS, 0) <> p.REJECTED_ROWS", VIEWS)
        self.assertIn("p.PROCESSED_ROWS IS NULL", VIEWS)
        self.assertIn("f.REJECTED_ROWS IS NULL", VIEWS)

    def test_pending_and_unloaded_local_gaps_are_not_false_success(self):
        self.assertIn("'PENDING_PROCESS'", VIEWS)
        self.assertIn("'RAW_COUNT_MISMATCH'", VIEWS)
        self.assertIn("'PROCESS_COUNT_MISMATCH'", VIEWS)
        self.assertIn("Local", VIEWS)
        self.assertIn("HEALTH_STATUS NOT IN ('RECONCILED', 'PENDING_PROCESS')", CHECKS)
        self.assertIn("WINDOW_STATUS = 'unresolved'", CHECKS)


if __name__ == "__main__":
    unittest.main()
