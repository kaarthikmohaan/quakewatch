"""Offline checks for the account metering profile guard."""

import tempfile
import unittest
from pathlib import Path

from scripts.phase4_usage import checked_admin_profile


class Phase4UsageTests(unittest.TestCase):
    def test_accepts_expected_profile_without_printing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[connections.quakewatch_admin]\naccount="demo"\nuser="owner"\n'
                            'password="dummy"\nrole="ACCOUNTADMIN"\n')
            self.assertEqual(checked_admin_profile(path)["role"], "ACCOUNTADMIN")

    def test_rejects_non_admin_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[connections.quakewatch_admin]\naccount="demo"\nuser="owner"\n'
                            'password="dummy"\nrole="QUAKEWATCH_ROLE"\n')
            with self.assertRaises(RuntimeError):
                checked_admin_profile(path)
