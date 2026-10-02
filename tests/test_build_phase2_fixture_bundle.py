"""Offline artifact checks for the isolated procedure fixture."""

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.fixtures.build_phase2_fixture_bundle import build_fixture_copy
from scripts.fixtures.phase2_fixture_namespace import SQL_FILES, TEST_DATABASE
from scripts.pipeline.build_procedure_bundle import MODULES


class FixtureBundleTest(unittest.TestCase):
    def test_copy_is_reproducible_and_contains_no_production_references(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            digest, count = build_fixture_copy(output)
            self.assertEqual(build_fixture_copy(output), (digest, count))
            self.assertEqual(count, len(MODULES) + len(SQL_FILES))
            with ZipFile(output / "quakewatch_procedure.zip") as archive:
                self.assertEqual(set(archive.namelist()),
                                 {f"quakewatch/{name}" for name in MODULES})
                bodies = [archive.read(name).decode() for name in archive.namelist()]
            sql_bodies = [(output / "sql" / name).read_text() for name in SQL_FILES]
            for body in bodies + sql_bodies:
                self.assertNotIn("QUAKEWATCH.RAW.", body)
                self.assertNotIn("QUAKEWATCH.CURATED.", body)
            self.assertIn(TEST_DATABASE + ".CURATED.FACT_EVENT_REVISION",
                          "\n".join(bodies))
            self.assertIn("@" + TEST_DATABASE + ".RAW.USGS_JSON_STAGE",
                          (output / "sql" / "setup/09_create_procedure.sql").read_text())


if __name__ == "__main__":
    unittest.main()
