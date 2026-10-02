"""Verify the offline procedure bundle and pinned SQL registration contract."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.pipeline.build_procedure_bundle import MODULES, REPO_ROOT, build_bundle


SQL = (REPO_ROOT / "sql" / "phase2_create_procedure.sql").read_text()


class ProcedureBundleTest(unittest.TestCase):
    def test_bundle_is_reproducible_and_importable_without_snowpark(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quakewatch_procedure.zip"
            first = build_bundle(output)
            self.assertEqual(build_bundle(output), first)
            with ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {f"quakewatch/{name}" for name in MODULES})
            env = {**os.environ, "PYTHONPATH": str(output)}
            result = subprocess.run(
                [sys.executable, "-c", "import quakewatch.snowpark_procedure"],
                cwd=directory, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_sql_pins_verified_runtime_and_import_path(self):
        for required in (
            "PROCESS_LOADED_ATTEMPT(ATTEMPT_ID VARCHAR)",
            "RUNTIME_VERSION = '3.12'",
            "snowflake-snowpark-python==1.55.0",
            "@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure/quakewatch_procedure.zip",
            "from quakewatch.snowpark_procedure import run",
            "EXECUTE AS OWNER",
        ):
            with self.subTest(required=required):
                self.assertIn(required, SQL)


if __name__ == "__main__":
    unittest.main()
