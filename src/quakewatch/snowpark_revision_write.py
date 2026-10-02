"""Deduplicated revision fact MERGE inside the model transaction."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from quakewatch.process_batch import BatchProjection, ProjectedObservation
from quakewatch.revisions import RevisionCandidate, deduplicate_revision_candidates
from quakewatch.snowpark_staging_write import MAX_ROWS_PER_MERGE

MERGE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.FACT_EVENT_REVISION t
USING (
    SELECT
        f.value:canonical_event_id::VARCHAR AS CANONICAL_EVENT_ID,
        TO_TIMESTAMP_TZ(f.value:source_updated_at::VARCHAR) AS SOURCE_UPDATED_AT,
        f.value:payload_hash::VARCHAR AS PAYLOAD_HASH,
        f.value:source_event_id::VARCHAR AS SOURCE_EVENT_ID,
        f.value:associated_ids AS ASSOCIATED_IDS,
        TO_TIMESTAMP_TZ(f.value:origin_time::VARCHAR) AS ORIGIN_TIME,
        TO_TIMESTAMP_TZ(f.value:fetched_at::VARCHAR) AS FETCHED_AT,
        CURRENT_TIMESTAMP() AS CURATED_AT,
        f.value:source_status::VARCHAR AS SOURCE_STATUS,
        TRY_TO_DOUBLE(f.value:magnitude::VARCHAR) AS MAGNITUDE,
        f.value:magnitude_type::VARCHAR AS MAGNITUDE_TYPE,
        f.value:place::VARCHAR AS PLACE,
        TRY_TO_DOUBLE(f.value:longitude::VARCHAR) AS LONGITUDE,
        TRY_TO_DOUBLE(f.value:latitude::VARCHAR) AS LATITUDE,
        TRY_TO_DOUBLE(f.value:depth_km::VARCHAR) AS DEPTH_KM,
        f.value:staging_parser_version::VARCHAR AS STAGING_PARSER_VERSION,
        f.value:stage_file_name::VARCHAR AS STAGE_FILE_NAME,
        f.value:stage_file_row_number::NUMBER(38, 0) AS STAGE_FILE_ROW_NUMBER
    FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f
) s
ON t.CANONICAL_EVENT_ID = s.CANONICAL_EVENT_ID
   AND t.SOURCE_UPDATED_AT = s.SOURCE_UPDATED_AT
   AND t.PAYLOAD_HASH = s.PAYLOAD_HASH
WHEN MATCHED AND s.FETCHED_AT > t.FETCHED_AT THEN UPDATE SET
    t.FETCHED_AT = s.FETCHED_AT,
    t.CURATED_AT = s.CURATED_AT,
    t.STAGE_FILE_NAME = s.STAGE_FILE_NAME,
    t.STAGE_FILE_ROW_NUMBER = s.STAGE_FILE_ROW_NUMBER
WHEN NOT MATCHED THEN INSERT (
    CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SOURCE_EVENT_ID,
    ASSOCIATED_IDS, ORIGIN_TIME, FETCHED_AT, CURATED_AT, SOURCE_STATUS,
    MAGNITUDE, MAGNITUDE_TYPE, PLACE, LONGITUDE, LATITUDE, DEPTH_KM,
    STAGING_PARSER_VERSION, STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER
) VALUES (
    s.CANONICAL_EVENT_ID, s.SOURCE_UPDATED_AT, s.PAYLOAD_HASH, s.SOURCE_EVENT_ID,
    s.ASSOCIATED_IDS, s.ORIGIN_TIME, s.FETCHED_AT, s.CURATED_AT, s.SOURCE_STATUS,
    s.MAGNITUDE, s.MAGNITUDE_TYPE, s.PLACE, s.LONGITUDE, s.LATITUDE, s.DEPTH_KM,
    s.STAGING_PARSER_VERSION, s.STAGE_FILE_NAME, s.STAGE_FILE_ROW_NUMBER
)
"""

KEY_CHECK_SQL = """
SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, COUNT(*) AS DUPLICATES
FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION
WHERE CANONICAL_EVENT_ID IN (
    SELECT VALUE::VARCHAR FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?)))
)
GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
HAVING COUNT(*) > 1
"""

ALIAS_REKEY_CHECK_SQL = """
SELECT DISTINCT SOURCE_EVENT_ID, CANONICAL_EVENT_ID
FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION
WHERE SOURCE_EVENT_ID IN (
    SELECT VALUE::VARCHAR FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?)))
)
"""


def _wire_row(item: ProjectedObservation, canonical_id: str) -> dict[str, Any]:
    fields, raw = item.fields, item.raw
    return {
        "canonical_event_id": canonical_id,
        "source_updated_at": fields["source_updated_at"].astimezone(UTC).isoformat(),
        "payload_hash": raw.payload_hash,
        "source_event_id": fields["source_event_id"],
        "associated_ids": fields["associated_ids"],
        "origin_time": fields["origin_time"].astimezone(UTC).isoformat(),
        "fetched_at": raw.fetched_at.astimezone(UTC).isoformat(),
        "source_status": fields["source_status"],
        "magnitude": fields["magnitude"],
        "magnitude_type": fields["magnitude_type"],
        "place": fields["place"],
        "longitude": fields["longitude"],
        "latitude": fields["latitude"],
        "depth_km": fields["depth_km"],
        "staging_parser_version": fields["staging_parser_version"],
        "stage_file_name": raw.stage_file_name,
        "stage_file_row_number": raw.stage_file_row_number,
    }


def selected_revision_observations(
    projection: BatchProjection, canonical_ids: dict[str, str]
) -> list[tuple[str, ProjectedObservation]]:
    """Choose one valid observation per canonical revision key."""
    by_source: dict[tuple[str, int], ProjectedObservation] = {}
    candidates = []
    for item in projection.observations:
        if item.fields["reject_reason"] is not None:
            continue
        source_id = item.fields["source_event_id"]
        canonical_id = canonical_ids.get(source_id)
        if not canonical_id:
            raise ValueError("canonical ID missing for a validated source event")
        raw = item.raw
        by_source[raw.source_key] = item
        candidates.append(RevisionCandidate(
            canonical_id, item.fields["source_updated_at"], raw.payload_hash,
            raw.fetched_at, raw.stage_file_name, raw.stage_file_row_number,
        ))
    return [
        (candidate.canonical_event_id, by_source[candidate.source_key])
        for candidate in deduplicate_revision_candidates(candidates)
    ]


def write_revision_fact(
    session: Any, projection: BatchProjection, canonical_ids: dict[str, str]
) -> int:
    """MERGE valid, deduplicated revisions; return actual inserted+updated rows.

    The caller must supply a map from all durable alias observations and handle
    any changed canonical keys for existing facts before invoking this writer.
    """
    selected = selected_revision_observations(projection, canonical_ids)
    affected_canonical = {canonical_id for canonical_id, _ in selected}
    affected_ids = sorted(
        source_id for source_id, canonical_id in canonical_ids.items()
        if canonical_id in affected_canonical
    )
    for start in range(0, len(affected_ids), MAX_ROWS_PER_MERGE):
        ids = affected_ids[start:start + MAX_ROWS_PER_MERGE]
        for result in session.sql(
            ALIAS_REKEY_CHECK_SQL, params=[json.dumps(ids)]
        ).collect():
            stored = result.as_dict()
            if canonical_ids[stored["SOURCE_EVENT_ID"]] != stored["CANONICAL_EVENT_ID"]:
                raise ValueError("alias rekey required before revision MERGE")
    changed = 0
    for start in range(0, len(selected), MAX_ROWS_PER_MERGE):
        chunk = selected[start:start + MAX_ROWS_PER_MERGE]
        body = json.dumps([
            _wire_row(item, canonical_id) for canonical_id, item in chunk
        ], separators=(",", ":"), allow_nan=False)
        rows = session.sql(MERGE_SQL, params=[body]).collect()
        if len(rows) != 1:
            raise ValueError("revision MERGE did not return one result row")
        counts = {key.lower(): value for key, value in rows[0].as_dict().items()}
        inserted, updated = counts.get("number of rows inserted"), counts.get("number of rows updated")
        if not isinstance(inserted, int) or not isinstance(updated, int):
            raise ValueError("revision MERGE result lacks inserted/updated counts")
        changed += inserted + updated
    canonical_set = sorted(affected_canonical)
    if canonical_set and session.sql(
        KEY_CHECK_SQL, params=[json.dumps(canonical_set)]
    ).collect():
        raise ValueError("duplicate canonical revision keys exist after MERGE")
    return changed
