"""Keep Phase 3 uniqueness SQL read-only and at the model's full grain."""

import re
import unittest
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "sql/checks/uniqueness.sql").read_text()


class Phase3UniquenessSqlTest(unittest.TestCase):
    def test_two_read_only_queries_use_full_grain(self):
        statements = [item.strip() for item in SQL.split(";") if item.strip()]
        self.assertEqual(len(statements), 2)
        self.assertTrue(all(re.search(r"\bSELECT\b", item) for item in statements))
        self.assertFalse(
            re.search(
                r"\b(CALL|CREATE|DELETE|INSERT|MERGE|UPDATE|DROP|TRUNCATE)\b",
                "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--")),
            )
        )
        keys = ("CANONICAL_EVENT_ID", "SOURCE_UPDATED_AT", "PAYLOAD_HASH")
        for statement in statements:
            self.assertIn(", ".join(keys), statement)
            self.assertIn("HAVING COUNT(*) > 1", statement)
        self.assertIn("SITE_KEY", statements[1])
        self.assertIn("QUAKEWATCH.CURATED.FACT_EVENT_REVISION", statements[0])
        self.assertIn("QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE", statements[1])


if __name__ == "__main__":
    unittest.main()
