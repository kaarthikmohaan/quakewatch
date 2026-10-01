"""Offline guards for the optional Phase 4 recovery preflight."""

import unittest

from scripts.phase4_recovery_preflight import validate


SOURCE = ("FACT_EVENT_REVISION", "BASE TABLE", "QUAKEWATCH_ROLE", 5, 1, "NO")


class RecoveryPreflightTests(unittest.TestCase):
    def test_accepts_expected_fixture(self) -> None:
        self.assertEqual(validate([SOURCE], 5, 0)["status"], "pass")

    def test_stops_on_unexpected_state(self) -> None:
        cases = (
            ([SOURCE, ("QW_PHASE4_REVISION_DEMO", "BASE TABLE", "QUAKEWATCH_ROLE", 5, 1, "NO")], 5, 0),
            ([SOURCE], 4, 0),
            ([SOURCE], 5, 1),
            ([("FACT_EVENT_REVISION", "BASE TABLE", "QUAKEWATCH_ROLE", 5, 0, "NO")], 5, 0),
        )
        for metadata, count, duplicates in cases:
            with self.subTest(metadata=metadata, count=count, duplicates=duplicates):
                with self.assertRaisesRegex(RuntimeError, "stop before clone"):
                    validate(metadata, count, duplicates)
