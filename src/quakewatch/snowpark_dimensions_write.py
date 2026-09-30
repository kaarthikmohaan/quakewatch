"""Populate the four small dimensions and revision-by-site bridge."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from quakewatch.process_batch import BatchProjection
from quakewatch.settings import SITES
from quakewatch.site_distance import distances_to_public_sites
from quakewatch.snowpark_revision_write import selected_revision_observations
from quakewatch.snowpark_staging_write import MAX_ROWS_PER_MERGE


DATE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.DIM_DATE t
USING (SELECT TO_DATE(f.value:date_key::VARCHAR) AS DATE_KEY,
              f.value:calendar_year::NUMBER(4, 0) AS CALENDAR_YEAR,
              f.value:calendar_month::NUMBER(2, 0) AS CALENDAR_MONTH
       FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f) s
ON t.DATE_KEY = s.DATE_KEY
WHEN NOT MATCHED THEN INSERT (DATE_KEY, CALENDAR_YEAR, CALENDAR_MONTH)
VALUES (s.DATE_KEY, s.CALENDAR_YEAR, s.CALENDAR_MONTH)
"""

SITE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.DIM_SITE t
USING (SELECT f.value:site_key::VARCHAR AS SITE_KEY,
              f.value:site_name::VARCHAR AS SITE_NAME,
              f.value:latitude::FLOAT AS LATITUDE,
              f.value:longitude::FLOAT AS LONGITUDE,
              f.value:radius_km::FLOAT AS RADIUS_KM
       FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f) s
ON t.SITE_KEY = s.SITE_KEY
WHEN NOT MATCHED THEN INSERT (SITE_KEY, SITE_NAME, LATITUDE, LONGITUDE, RADIUS_KM)
VALUES (s.SITE_KEY, s.SITE_NAME, s.LATITUDE, s.LONGITUDE, s.RADIUS_KM)
"""

MAGNITUDE_TYPE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.DIM_MAGNITUDE_TYPE t
USING (SELECT f.value::VARCHAR AS MAGNITUDE_TYPE
       FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f) s
ON t.MAGNITUDE_TYPE = s.MAGNITUDE_TYPE
WHEN NOT MATCHED THEN INSERT (MAGNITUDE_TYPE) VALUES (s.MAGNITUDE_TYPE)
"""

STATUS_SQL = """
MERGE INTO QUAKEWATCH.CURATED.DIM_EVENT_STATUS t
USING (SELECT f.value::VARCHAR AS SOURCE_STATUS
       FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f) s
ON t.SOURCE_STATUS = s.SOURCE_STATUS
WHEN NOT MATCHED THEN INSERT (SOURCE_STATUS) VALUES (s.SOURCE_STATUS)
"""

BRIDGE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE t
USING (
    SELECT f.value:canonical_event_id::VARCHAR AS CANONICAL_EVENT_ID,
           TO_TIMESTAMP_TZ(f.value:source_updated_at::VARCHAR) AS SOURCE_UPDATED_AT,
           f.value:payload_hash::VARCHAR AS PAYLOAD_HASH,
           f.value:site_key::VARCHAR AS SITE_KEY,
           TRY_TO_DOUBLE(f.value:epicentral_distance_km::VARCHAR) AS EPICENTRAL_DISTANCE_KM,
           f.value:within_radius::BOOLEAN AS WITHIN_RADIUS
    FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f
) s
ON t.CANONICAL_EVENT_ID = s.CANONICAL_EVENT_ID
   AND t.SOURCE_UPDATED_AT = s.SOURCE_UPDATED_AT
   AND t.PAYLOAD_HASH = s.PAYLOAD_HASH
   AND t.SITE_KEY = s.SITE_KEY
WHEN MATCHED THEN UPDATE SET
    t.EPICENTRAL_DISTANCE_KM = s.EPICENTRAL_DISTANCE_KM,
    t.WITHIN_RADIUS = s.WITHIN_RADIUS
WHEN NOT MATCHED THEN INSERT (
    CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY,
    EPICENTRAL_DISTANCE_KM, WITHIN_RADIUS
) VALUES (
    s.CANONICAL_EVENT_ID, s.SOURCE_UPDATED_AT, s.PAYLOAD_HASH, s.SITE_KEY,
    s.EPICENTRAL_DISTANCE_KM, s.WITHIN_RADIUS
)
"""

BRIDGE_KEY_CHECK_SQL = """
SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY, COUNT(*) AS DUPLICATES
FROM QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE
WHERE CANONICAL_EVENT_ID IN (
    SELECT VALUE::VARCHAR FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?)))
)
GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY
HAVING COUNT(*) > 1
"""


def _merge_chunks(session: Any, sql: str, rows: list[Any]) -> None:
    for start in range(0, len(rows), MAX_ROWS_PER_MERGE):
        body = json.dumps(rows[start:start + MAX_ROWS_PER_MERGE],
                          separators=(",", ":"), allow_nan=False)
        session.sql(sql, params=[body]).collect()


def write_dimensions_and_bridge(
    session: Any, projection: BatchProjection, canonical_ids: dict[str, str]
) -> int:
    """MERGE dimensions and exactly one bridge row per selected revision/site."""
    selected = selected_revision_observations(projection, canonical_ids)
    dates = set()
    magnitude_types = set()
    statuses = set()
    bridge = []
    for canonical_id, item in selected:
        fields = item.fields
        dates.add(fields["origin_time"].astimezone(UTC).date())
        dates.add(fields["source_updated_at"].astimezone(UTC).date())
        if fields["magnitude_type"] is not None:
            magnitude_types.add(fields["magnitude_type"])
        statuses.add(fields["source_status"])
        for site in distances_to_public_sites(fields["longitude"], fields["latitude"]):
            bridge.append({
                "canonical_event_id": canonical_id,
                "source_updated_at": fields["source_updated_at"].astimezone(UTC).isoformat(),
                "payload_hash": item.raw.payload_hash,
                "site_key": site.site_key,
                "epicentral_distance_km": site.epicentral_distance_km,
                "within_radius": site.within_radius,
            })
    _merge_chunks(session, DATE_SQL, [
        {"date_key": day.isoformat(), "calendar_year": day.year,
         "calendar_month": day.month} for day in sorted(dates)
    ])
    _merge_chunks(session, SITE_SQL, [
        {"site_key": key, "site_name": site.name, "latitude": site.latitude,
         "longitude": site.longitude, "radius_km": site.radius_km}
        for key, site in sorted(SITES.items())
    ])
    _merge_chunks(session, MAGNITUDE_TYPE_SQL, sorted(magnitude_types))
    _merge_chunks(session, STATUS_SQL, sorted(statuses))
    _merge_chunks(session, BRIDGE_SQL, bridge)
    canonical_set = sorted({canonical_id for canonical_id, _ in selected})
    for start in range(0, len(canonical_set), MAX_ROWS_PER_MERGE):
        canonical_chunk = canonical_set[start:start + MAX_ROWS_PER_MERGE]
        if session.sql(
            BRIDGE_KEY_CHECK_SQL, params=[json.dumps(canonical_chunk)]
        ).collect():
            raise ValueError("duplicate event-site bridge keys exist after MERGE")
    return len(bridge)
