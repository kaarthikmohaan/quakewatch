"""Local DDL checks for the minimal Phase 2 dimensions and site bridge."""

import unittest
from pathlib import Path


SQL = (Path(__file__).resolve().parents[1] / "sql/phase2_dimensions_bridge.sql").read_text()


class DimensionSqlContractTest(unittest.TestCase):
    def test_only_design_dimensions_are_defined(self) -> None:
        for name in (
            "DIM_DATE", "DIM_SITE", "DIM_MAGNITUDE_TYPE", "DIM_EVENT_STATUS",
        ):
            with self.subTest(name=name):
                self.assertIn(f"CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.{name}", SQL)
        self.assertEqual(SQL.count("CREATE TABLE IF NOT EXISTS"), 5)

    def test_bridge_has_full_revision_and_site_grain(self) -> None:
        bridge = SQL.split("QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE (", 1)[1]
        for column in (
            "CANONICAL_EVENT_ID VARCHAR NOT NULL",
            "SOURCE_UPDATED_AT TIMESTAMP_TZ NOT NULL",
            "PAYLOAD_HASH VARCHAR(64) NOT NULL",
            "SITE_KEY VARCHAR NOT NULL",
            "EPICENTRAL_DISTANCE_KM FLOAT",
            "WITHIN_RADIUS BOOLEAN",
        ):
            with self.subTest(column=column):
                self.assertIn(column, bridge)


if __name__ == "__main__":
    unittest.main()
