"""Keep CI secret-free and the sample analysis bounded to public data."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text()
SAMPLE = (ROOT / "sql/phase3_sample_analysis.sql").read_text()


class Phase3CiSampleTest(unittest.TestCase):
    def test_ci_uses_locked_install_without_snowflake_secrets(self):
        self.assertIn("uv sync --locked --no-editable", WORKFLOW)
        self.assertIn("python -m unittest discover -s tests", WORKFLOW)
        self.assertIn("python-version: \"3.12\"", WORKFLOW)
        self.assertIn("contents: read", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)
        self.assertNotIn("snow sql", WORKFLOW)

    def test_ci_builds_ignored_synthetic_fixtures_before_tests(self):
        bundle = WORKFLOW.index("scripts/fixtures/build_phase2_fixture_bundle.py")
        first = WORKFLOW.index("scripts/fixtures/build_phase2_fixture_attempts.py")
        second = WORKFLOW.index("scripts/fixtures/build_phase2_old_origin_attempts.py")
        tests = WORKFLOW.index("python -m unittest discover -s tests")
        self.assertLess(bundle, first)
        self.assertLess(first, second)
        self.assertLess(second, tests)

    def test_sample_joins_full_revision_key_with_public_bounds(self):
        self.assertIn("e.CANONICAL_EVENT_ID = b.CANONICAL_EVENT_ID", SAMPLE)
        self.assertIn("e.SOURCE_UPDATED_AT = b.SOURCE_UPDATED_AT", SAMPLE)
        self.assertIn("e.PAYLOAD_HASH = b.PAYLOAD_HASH", SAMPLE)
        self.assertIn("b.SITE_KEY = 'seattle'", SAMPLE)
        self.assertIn("2026-09-28T00:00:00Z", SAMPLE)
        self.assertIn("2026-09-29T00:00:00Z", SAMPLE)
        self.assertNotIn("SELECT *", SAMPLE)


if __name__ == "__main__":
    unittest.main()
