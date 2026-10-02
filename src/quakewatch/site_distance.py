"""Horizontal epicentral distance to the three public example sites."""

from __future__ import annotations

import math
from dataclasses import dataclass

from quakewatch.settings import SITES

# IUGG mean Earth radius. This is a spherical horizontal approximation.
MEAN_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class SiteDistance:
    site_key: str
    epicentral_distance_km: float | None
    within_radius: bool | None


def _check_point(longitude: float, latitude: float) -> None:
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("longitude must be finite and within -180..180")
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("latitude must be finite and within -90..90")


def great_circle_km(
    longitude_a: float, latitude_a: float, longitude_b: float, latitude_b: float
) -> float:
    """Haversine distance on a sphere using longitude/latitude in degrees."""
    _check_point(longitude_a, latitude_a)
    _check_point(longitude_b, latitude_b)
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * MEAN_EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


def distances_to_public_sites(
    longitude: float | None, latitude: float | None
) -> list[SiteDistance]:
    """Return one bridge value per configured site, including null geometry."""
    if (longitude is None) != (latitude is None):
        raise ValueError("longitude and latitude must both be present or both null")
    if longitude is not None and latitude is not None:
        _check_point(longitude, latitude)
    rows = []
    for site_key, site in SITES.items():
        distance = (
            None if longitude is None or latitude is None else
            great_circle_km(longitude, latitude, site.longitude, site.latitude)
        )
        rows.append(SiteDistance(
            site_key=site_key,
            epicentral_distance_km=distance,
            within_radius=None if distance is None else distance <= site.radius_km,
        ))
    return rows
