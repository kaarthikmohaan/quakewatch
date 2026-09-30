"""Pure typed projection used by the future in-Snowflake Snowpark procedure."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


STAGING_PARSER_VERSION = "1"


def _epoch_ms(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def project_feature(feature: Any) -> dict[str, Any]:
    """Return typed fields and one deterministic reject reason, if invalid.

    The caller retains the original RAW payload and its file-row lineage. This
    function does not deduplicate, choose aliases, or select a current revision.
    """
    result: dict[str, Any] = {
        "staging_parser_version": STAGING_PARSER_VERSION,
        "source_event_id": None,
        "origin_time": None,
        "source_updated_at": None,
        "source_status": None,
        "associated_ids": None,
        "magnitude": None,
        "magnitude_type": None,
        "place": None,
        "longitude": None,
        "latitude": None,
        "depth_km": None,
        "reject_reason": None,
    }

    def reject(reason: str) -> dict[str, Any]:
        result["reject_reason"] = reason
        return result

    if not isinstance(feature, dict):
        return reject("invalid_feature")
    source_id = feature.get("id")
    if not isinstance(source_id, str) or not source_id.strip():
        return reject("invalid_source_event_id")
    result["source_event_id"] = source_id

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return reject("invalid_properties")
    for source, target in (("time", "origin_time"), ("updated", "source_updated_at")):
        parsed = _epoch_ms(properties.get(source))
        if parsed is None:
            return reject(f"invalid_{target}")
        result[target] = parsed

    status = properties.get("status")
    if not isinstance(status, str) or not status.strip():
        return reject("invalid_source_status")
    result["source_status"] = status

    ids = properties.get("ids")
    if ids is not None:
        if isinstance(ids, str):
            result["associated_ids"] = [item for item in ids.split(",") if item]
        elif isinstance(ids, list) and all(isinstance(item, str) for item in ids):
            result["associated_ids"] = ids.copy()
        else:
            return reject("invalid_associated_ids")

    magnitude = properties.get("mag")
    if magnitude is not None:
        result["magnitude"] = _number(magnitude)
        if result["magnitude"] is None:
            return reject("invalid_magnitude")
    for source, target in (("magType", "magnitude_type"), ("place", "place")):
        value = properties.get(source)
        if value is not None and not isinstance(value, str):
            return reject(f"invalid_{target}")
        result[target] = value

    geometry = feature.get("geometry")
    if geometry is None and status == "deleted":
        return result
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return reject("invalid_geometry")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) not in (2, 3):
        return reject("invalid_geometry")
    longitude, latitude = _number(coordinates[0]), _number(coordinates[1])
    if longitude is None or not -180 <= longitude <= 180:
        return reject("invalid_longitude")
    if latitude is None or not -90 <= latitude <= 90:
        return reject("invalid_latitude")
    result["longitude"], result["latitude"] = longitude, latitude
    if len(coordinates) == 3 and coordinates[2] is not None:
        result["depth_km"] = _number(coordinates[2])
        if result["depth_km"] is None:
            return reject("invalid_depth_km")
    return result
