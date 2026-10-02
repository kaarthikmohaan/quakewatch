"""Offline scope checks for the proposed test-database setup SQL."""

import re
import unittest

from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE
from scripts.pipeline.build_procedure_bundle import REPO_ROOT

SQL = (REPO_ROOT / "sql" / "demos/fixture_setup.sql").read_text()


class FixtureSetupSqlTest(unittest.TestCase):
    def test_creates_only_new_fixture_database_and_schemas(self):
        self.assertIn(f"CREATE DATABASE {TEST_DATABASE};", SQL)
        self.assertNotIn("CREATE DATABASE IF NOT EXISTS", SQL)
        self.assertEqual(re.findall(r"(?m)^CREATE DATABASE .*;", SQL),
                         [f"CREATE DATABASE {TEST_DATABASE};"])
        self.assertEqual(re.findall(r"(?m)^CREATE SCHEMA .*;", SQL),
                         [f"CREATE SCHEMA {TEST_DATABASE}.RAW;",
                          f"CREATE SCHEMA {TEST_DATABASE}.CURATED;"])
        self.assertNotRegex(SQL, r"(?m)^(?:DROP|ALTER|DELETE|TRUNCATE|REPLACE)\b")

    def test_grants_only_project_role_access_to_fixture_schemas(self):
        statements = [line for line in SQL.splitlines() if line.startswith("GRANT ")]
        self.assertEqual(len(statements), 8)
        for statement in statements:
            self.assertIn(TEST_DATABASE, statement)
            self.assertTrue(statement.endswith("TO ROLE QUAKEWATCH_ROLE;"))
        self.assertNotIn("QUAKEWATCH.RAW.", SQL)
        self.assertNotIn("QUAKEWATCH.CURATED.", SQL)


if __name__ == "__main__":
    unittest.main()
