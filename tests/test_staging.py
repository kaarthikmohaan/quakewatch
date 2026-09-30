"""Fixture checks for the pure Phase 2 source-feature projection."""

import copy
import json
import unittest
from datetime import UTC
from pathlib import Path

from quakewatch.staging import STAGING_PARSER_VERSION, project_feature


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class StagingProjectionTest(unittest.TestCase):
    def test_normal_feature_keeps_source_unchanged(self) -> None:
        feature = fixture("normal_event.json")
        original = copy.deepcopy(feature)
        row = project_feature(feature)
        self.assertEqual(feature, original)
        self.assertIsNone(row["reject_reason"])
        self.assertEqual(row["staging_parser_version"], STAGING_PARSER_VERSION)
        self.assertEqual(row["source_event_id"], "uw714110682")
        self.assertEqual(row["associated_ids"], ["uw714110682"])
        self.assertEqual(row["origin_time"].tzinfo, UTC)
        self.assertAlmostEqual(row["longitude"], -121.516666666667)

    def test_deleted_feature_may_have_no_geometry(self) -> None:
        feature = fixture("deleted_event.json")
        feature["geometry"] = None
        row = project_feature(feature)
        self.assertIsNone(row["reject_reason"])
        self.assertEqual(row["source_status"], "deleted")
        self.assertIsNone(row["longitude"])

    def test_missing_id_and_bad_clock_are_rejected(self) -> None:
        feature = fixture("normal_event.json")
        feature["id"] = ""
        self.assertEqual(project_feature(feature)["reject_reason"], "invalid_source_event_id")
        feature["id"] = "uw714110682"
        feature["properties"]["updated"] = True
        self.assertEqual(project_feature(feature)["reject_reason"], "invalid_source_updated_at")

    def test_active_feature_needs_valid_point(self) -> None:
        feature = fixture("normal_event.json")
        feature["geometry"]["coordinates"][1] = 91
        self.assertEqual(project_feature(feature)["reject_reason"], "invalid_latitude")
        feature["geometry"] = None
        self.assertEqual(project_feature(feature)["reject_reason"], "invalid_geometry")

    def test_optional_fields_and_additive_payload(self) -> None:
        feature = fixture("additive_field_event.json")
        feature["properties"]["mag"] = None
        row = project_feature(feature)
        self.assertIsNone(row["reject_reason"])
        self.assertIsNone(row["magnitude"])
        self.assertIn("future_catalog_field", feature["properties"])

    def test_nonfinite_magnitude_is_rejected(self) -> None:
        feature = fixture("normal_event.json")
        feature["properties"]["mag"] = float("nan")
        self.assertEqual(project_feature(feature)["reject_reason"], "invalid_magnitude")


if __name__ == "__main__":
    unittest.main()
