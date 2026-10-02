"""Offline guard tests for optional demo-clone deletion."""

import unittest

from scripts.evidence.phase4.clone_cleanup import validate_cleanup


class CloneCleanupTests(unittest.TestCase):
    def test_accepts_recorded_state(self) -> None:
        validate_cleanup(5, 5, 1, 1)

    def test_stops_on_changed_state(self) -> None:
        for counts in ((5, 4, 1, 1), (5, 5, 0, 1), (5, 5, 1, 0)):
            with self.subTest(counts=counts):
                with self.assertRaisesRegex(RuntimeError, "do not drop"):
                    validate_cleanup(*counts)
