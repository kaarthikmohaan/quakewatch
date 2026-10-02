"""Offline checks for the admin-only, read-only fixture name preflight."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.evidence.phase2.phase2_fixture_name_check import admin_params, check_name, main
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE


class FixtureNameCheckTest(unittest.TestCase):
    def test_admin_profile_is_narrow_and_password_is_not_printed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[connections.quakewatch_admin]\naccount="example"\nuser="u"\n'
                            'password="private"\nrole="ACCOUNTADMIN"\nwarehouse="COMPUTE_WH"\n')
            self.assertEqual(admin_params(path),
                             {"account": "example", "user": "u", "password": "private",
                              "role": "ACCOUNTADMIN"})
            path.write_text(path.read_text().replace("ACCOUNTADMIN", "PUBLIC"))
            with self.assertRaisesRegex(ValueError, "ACCOUNTADMIN"):
                admin_params(path)

    def test_preview_never_connects(self):
        output = io.StringIO()
        with patch("sys.argv", ["phase2_fixture_name_check.py"]), \
             patch("scripts.evidence.phase2.phase2_fixture_name_check.check_name",
                   side_effect=AssertionError("connected")), \
             contextlib.redirect_stdout(output):
            main()
        self.assertIn("no Snowflake connection", output.getvalue())

    def test_exact_name_only_blocks_setup(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("name",)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch("scripts.evidence.phase2.phase2_fixture_name_check.admin_params",
                   return_value={"account": "a", "user": "u", "password": "p",
                                 "role": "ACCOUNTADMIN"}), \
             patch("snowflake.connector.connect", return_value=connection):
            cursor.fetchall.return_value = [("QUAKEWATCHXPHASE2XFIXTURE",)]
            self.assertFalse(check_name(Path("unused")))
            cursor.fetchall.return_value = [(TEST_DATABASE,)]
            self.assertTrue(check_name(Path("unused")))
        cursor.execute.assert_called_with(f"SHOW DATABASES LIKE '{TEST_DATABASE}'")


if __name__ == "__main__":
    unittest.main()
