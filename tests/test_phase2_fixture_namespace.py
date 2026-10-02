"""Keep a test-only procedure copy away from production database objects."""

import contextlib
import io
import unittest

from scripts.fixtures.phase2_fixture_namespace import (
    TEST_DATABASE, inputs, main, validate_all, validate_and_rewrite,
)


class FixtureNamespaceTest(unittest.TestCase):
    def test_every_bundle_module_and_ddl_file_validates(self):
        counts = validate_all()
        self.assertGreater(sum(counts.values()), 0)
        self.assertIn("quakewatch/snowpark_revision_write.py", counts)
        self.assertIn("sql/phase2_create_procedure.sql", counts)
        for path, source in inputs().items():
            rewritten, count = validate_and_rewrite(path, source)
            self.assertNotIn("QUAKEWATCH.RAW.", rewritten)
            self.assertNotIn("QUAKEWATCH.CURATED.", rewritten)
            self.assertEqual(count, counts[path])
            if count:
                self.assertIn(TEST_DATABASE + ".", rewritten)

    def test_unexpected_database_or_schema_stops(self):
        for source in ("SELECT * FROM OTHERDB.RAW.EVENTS",
                       "SELECT * FROM QUAKEWATCH.PUBLIC.EVENTS"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "unexpected"):
                validate_and_rewrite("sample.sql", source)

    def test_stage_import_uses_test_database(self):
        source = inputs()["sql/phase2_create_procedure.sql"]
        rewritten, _count = validate_and_rewrite("sql/phase2_create_procedure.sql", source)
        self.assertIn("@QUAKEWATCH_PHASE2_FIXTURE.RAW.USGS_JSON_STAGE", rewritten)
        self.assertNotIn("@QUAKEWATCH.RAW.USGS_JSON_STAGE", rewritten)

    def test_preview_reports_only_offline_validation(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())
        self.assertIn(TEST_DATABASE, output.getvalue())


if __name__ == "__main__":
    unittest.main()
