"""Horizontal distance and site-radius behavior for the bridge."""

import unittest
from unittest.mock import patch

from quakewatch.settings import SITES, Site
from quakewatch.site_distance import distances_to_public_sites, great_circle_km


class SiteDistanceTest(unittest.TestCase):
    def test_same_point_is_zero_and_other_sites_are_outside(self) -> None:
        seattle = SITES["seattle"]
        rows = {row.site_key: row for row in distances_to_public_sites(
            seattle.longitude, seattle.latitude
        )}
        self.assertEqual(set(rows), set(SITES))
        self.assertAlmostEqual(rows["seattle"].epicentral_distance_km, 0.0)
        self.assertTrue(rows["seattle"].within_radius)
        self.assertFalse(rows["san-francisco"].within_radius)

    def test_antimeridian_uses_short_route(self) -> None:
        self.assertAlmostEqual(great_circle_km(179, 0, -179, 0), 222.390, places=2)

    def test_point_exactly_on_radius_boundary_is_included(self) -> None:
        with patch.dict(SITES, {"boundary": Site("Boundary", 0, 0, 0)}, clear=True):
            self.assertTrue(distances_to_public_sites(0, 0)[0].within_radius)

    def test_null_deleted_geometry_keeps_three_bridge_rows(self) -> None:
        rows = distances_to_public_sites(None, None)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.epicentral_distance_km is None for row in rows))
        self.assertTrue(all(row.within_radius is None for row in rows))

    def test_invalid_coordinates_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "latitude"):
            distances_to_public_sites(0, 91)
        with self.assertRaisesRegex(ValueError, "both"):
            distances_to_public_sites(None, 0)


if __name__ == "__main__":
    unittest.main()
