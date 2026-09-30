"""Bounded, idempotent staging MERGE for the in-Snowflake procedure."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from quakewatch.process_batch import BatchProjection, ProjectedObservation


MAX_ROWS_PER_MERGE = 500

EXISTING_SQL = """
SELECT STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER, ATTEMPT_ID, PAYLOAD_HASH,
       RAW_PARSER_VERSION, STAGING_PARSER_VERSION
FROM QUAKEWATCH.CURATED.STG_EVENT_REVISION
WHERE ATTEMPT_ID = ?
"""

MERGE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.STG_EVENT_REVISION t
USING (
    SELECT
        f.value:stage_file_name::VARCHAR AS STAGE_FILE_NAME,
        f.value:stage_file_row_number::NUMBER(38, 0) AS STAGE_FILE_ROW_NUMBER,
        f.value:attempt_id::VARCHAR AS ATTEMPT_ID,
        f.value:window_id::VARCHAR AS WINDOW_ID,
        TO_TIMESTAMP_TZ(f.value:fetched_at::VARCHAR) AS FETCHED_AT,
        f.value:payload_hash::VARCHAR AS PAYLOAD_HASH,
        f.value:raw_parser_version::VARCHAR AS RAW_PARSER_VERSION,
        f.value:staging_parser_version::VARCHAR AS STAGING_PARSER_VERSION,
        f.value:source_event_id::VARCHAR AS SOURCE_EVENT_ID,
        TRY_TO_TIMESTAMP_TZ(f.value:origin_time::VARCHAR) AS ORIGIN_TIME,
        TRY_TO_TIMESTAMP_TZ(f.value:source_updated_at::VARCHAR) AS SOURCE_UPDATED_AT,
        f.value:source_status::VARCHAR AS SOURCE_STATUS,
        f.value:associated_ids AS ASSOCIATED_IDS,
        TRY_TO_DOUBLE(f.value:magnitude::VARCHAR) AS MAGNITUDE,
        f.value:magnitude_type::VARCHAR AS MAGNITUDE_TYPE,
        f.value:place::VARCHAR AS PLACE,
        TRY_TO_DOUBLE(f.value:longitude::VARCHAR) AS LONGITUDE,
        TRY_TO_DOUBLE(f.value:latitude::VARCHAR) AS LATITUDE,
        TRY_TO_DOUBLE(f.value:depth_km::VARCHAR) AS DEPTH_KM,
        f.value:reject_reason::VARCHAR AS REJECT_REASON,
        CURRENT_TIMESTAMP() AS PROJECTED_AT
    FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f
) s
ON t.STAGE_FILE_NAME = s.STAGE_FILE_NAME
   AND t.STAGE_FILE_ROW_NUMBER = s.STAGE_FILE_ROW_NUMBER
WHEN NOT MATCHED THEN INSERT (
    STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER, ATTEMPT_ID, WINDOW_ID, FETCHED_AT,
    PAYLOAD_HASH, RAW_PARSER_VERSION, STAGING_PARSER_VERSION, SOURCE_EVENT_ID,
    ORIGIN_TIME, SOURCE_UPDATED_AT, SOURCE_STATUS, ASSOCIATED_IDS, MAGNITUDE,
    MAGNITUDE_TYPE, PLACE, LONGITUDE, LATITUDE, DEPTH_KM, REJECT_REASON, PROJECTED_AT
) VALUES (
    s.STAGE_FILE_NAME, s.STAGE_FILE_ROW_NUMBER, s.ATTEMPT_ID, s.WINDOW_ID, s.FETCHED_AT,
    s.PAYLOAD_HASH, s.RAW_PARSER_VERSION, s.STAGING_PARSER_VERSION, s.SOURCE_EVENT_ID,
    s.ORIGIN_TIME, s.SOURCE_UPDATED_AT, s.SOURCE_STATUS, s.ASSOCIATED_IDS, s.MAGNITUDE,
    s.MAGNITUDE_TYPE, s.PLACE, s.LONGITUDE, s.LATITUDE, s.DEPTH_KM, s.REJECT_REASON,
    s.PROJECTED_AT
)
"""

COUNT_SQL = """
SELECT COUNT(*) AS ROW_COUNT
FROM QUAKEWATCH.CURATED.STG_EVENT_REVISION
WHERE ATTEMPT_ID = ?
"""


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _wire_row(item: ProjectedObservation) -> dict[str, Any]:
    raw, fields = item.raw, item.fields
    return {
        "stage_file_name": raw.stage_file_name,
        "stage_file_row_number": raw.stage_file_row_number,
        "attempt_id": raw.attempt_id,
        "window_id": raw.window_id,
        "fetched_at": _iso(raw.fetched_at),
        "payload_hash": raw.payload_hash,
        "raw_parser_version": raw.raw_parser_version,
        **{key: _iso(value) if isinstance(value, datetime) else value
           for key, value in fields.items()},
    }


def write_staging(session: Any, projection: BatchProjection) -> int:
    """MERGE every projected row, then require exact per-attempt row count.

    The caller owns an open transaction. A parser-version or payload conflict
    under an existing source key needs an explicit replay/migration decision.
    """
    expected = {item.raw.source_key: item for item in projection.observations}
    existing_rows = session.sql(EXISTING_SQL, params=[projection.attempt_id]).collect()
    if len(existing_rows) != len({
        (row.as_dict()["STAGE_FILE_NAME"], row.as_dict()["STAGE_FILE_ROW_NUMBER"])
        for row in existing_rows
    }):
        raise ValueError("duplicate staged file-row key already exists")
    for row in existing_rows:
        stored = row.as_dict()
        key = (stored["STAGE_FILE_NAME"], stored["STAGE_FILE_ROW_NUMBER"])
        item = expected.get(key)
        if item is None or (
            stored["ATTEMPT_ID"], stored["PAYLOAD_HASH"], stored["RAW_PARSER_VERSION"],
            stored["STAGING_PARSER_VERSION"],
        ) != (
            projection.attempt_id, item.raw.payload_hash, item.raw.raw_parser_version,
            item.fields["staging_parser_version"],
        ):
            raise ValueError("existing staging row conflicts with RAW projection")

    observations = projection.observations
    for start in range(0, len(observations), MAX_ROWS_PER_MERGE):
        chunk = observations[start:start + MAX_ROWS_PER_MERGE]
        body = json.dumps([_wire_row(item) for item in chunk], separators=(",", ":"),
                          allow_nan=False)
        session.sql(MERGE_SQL, params=[body]).collect()
    count_rows = session.sql(COUNT_SQL, params=[projection.attempt_id]).collect()
    if len(count_rows) != 1 or count_rows[0].as_dict()["ROW_COUNT"] != projection.processed_rows:
        raise ValueError("staging row count does not match processed RAW rows")
    return projection.processed_rows
