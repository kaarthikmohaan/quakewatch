"""Merge one successfully curated extract/load attempt into FACT_BATCH_RUN."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from quakewatch.process_batch import BatchProjection

RECEIPT_SQL = """
SELECT ATTEMPT_ID, LOGICAL_BATCH_ID, BATCH_KIND, SITE_KEY,
       REQUESTED_STARTTIME, REQUESTED_ENDTIME, FETCHED_AT, RECORDED_AT,
       SOURCE_ROWS_RETURNED, RAW_ROWS_WRITTEN, LOADED_ROWS,
       EXTRACT_STATUS, LOAD_STATUS, COVERAGE_GAPS
FROM QUAKEWATCH.RAW.BATCH_ATTEMPT
WHERE ATTEMPT_ID = ?
"""

EXISTING_SQL = """
SELECT ATTEMPT_ID, LOGICAL_BATCH_ID
FROM QUAKEWATCH.CURATED.FACT_BATCH_RUN
WHERE ATTEMPT_ID = ?
"""

MERGE_SQL = """
MERGE INTO QUAKEWATCH.CURATED.FACT_BATCH_RUN t
USING (
    SELECT f.value:attempt_id::VARCHAR AS ATTEMPT_ID,
           f.value:logical_batch_id::VARCHAR AS LOGICAL_BATCH_ID,
           f.value:batch_kind::VARCHAR AS BATCH_KIND,
           f.value:site_key::VARCHAR AS SITE_KEY,
           TO_TIMESTAMP_TZ(f.value:requested_starttime::VARCHAR) AS REQUESTED_STARTTIME,
           TO_TIMESTAMP_TZ(f.value:requested_endtime::VARCHAR) AS REQUESTED_ENDTIME,
           TO_TIMESTAMP_TZ(f.value:fetched_at::VARCHAR) AS FETCHED_AT,
           TO_TIMESTAMP_TZ(f.value:raw_recorded_at::VARCHAR) AS RAW_RECORDED_AT,
           TO_TIMESTAMP_TZ(f.value:curated_at::VARCHAR) AS CURATED_AT,
           f.value:source_rows_returned::NUMBER(38, 0) AS SOURCE_ROWS_RETURNED,
           f.value:raw_rows_written::NUMBER(38, 0) AS RAW_ROWS_WRITTEN,
           f.value:loaded_rows::NUMBER(38, 0) AS LOADED_ROWS,
           f.value:processed_rows::NUMBER(38, 0) AS PROCESSED_ROWS,
           f.value:rejected_rows::NUMBER(38, 0) AS REJECTED_ROWS,
           TRY_TO_DECIMAL(f.value:fetch_to_curated_seconds::VARCHAR, 38, 3)
               AS FETCH_TO_CURATED_SECONDS,
           f.value:extract_status::VARCHAR AS EXTRACT_STATUS,
           f.value:load_status::VARCHAR AS LOAD_STATUS,
           f.value:process_status::VARCHAR AS PROCESS_STATUS,
           f.value:last_process_attempt_id::VARCHAR AS LAST_PROCESS_ATTEMPT_ID,
           f.value:coverage_gaps AS COVERAGE_GAPS,
           f.value:reconciliation_ok::BOOLEAN AS RECONCILIATION_OK,
           CURRENT_TIMESTAMP() AS UPDATED_AT
    FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f
) s
ON t.ATTEMPT_ID = s.ATTEMPT_ID
WHEN MATCHED THEN UPDATE SET
    t.PROCESSED_ROWS = s.PROCESSED_ROWS,
    t.REJECTED_ROWS = s.REJECTED_ROWS,
    t.CURATED_AT = s.CURATED_AT,
    t.FETCH_TO_CURATED_SECONDS = s.FETCH_TO_CURATED_SECONDS,
    t.PROCESS_STATUS = s.PROCESS_STATUS,
    t.LAST_PROCESS_ATTEMPT_ID = s.LAST_PROCESS_ATTEMPT_ID,
    t.UPDATED_AT = s.UPDATED_AT
WHEN NOT MATCHED THEN INSERT (
    ATTEMPT_ID, LOGICAL_BATCH_ID, BATCH_KIND, SITE_KEY, REQUESTED_STARTTIME,
    REQUESTED_ENDTIME, FETCHED_AT, RAW_RECORDED_AT, CURATED_AT,
    SOURCE_ROWS_RETURNED, RAW_ROWS_WRITTEN, LOADED_ROWS, PROCESSED_ROWS,
    REJECTED_ROWS, FETCH_TO_CURATED_SECONDS, EXTRACT_STATUS, LOAD_STATUS,
    PROCESS_STATUS, LAST_PROCESS_ATTEMPT_ID, COVERAGE_GAPS, RECONCILIATION_OK, UPDATED_AT
) VALUES (
    s.ATTEMPT_ID, s.LOGICAL_BATCH_ID, s.BATCH_KIND, s.SITE_KEY, s.REQUESTED_STARTTIME,
    s.REQUESTED_ENDTIME, s.FETCHED_AT, s.RAW_RECORDED_AT, s.CURATED_AT,
    s.SOURCE_ROWS_RETURNED, s.RAW_ROWS_WRITTEN, s.LOADED_ROWS, s.PROCESSED_ROWS,
    s.REJECTED_ROWS, s.FETCH_TO_CURATED_SECONDS, s.EXTRACT_STATUS, s.LOAD_STATUS,
    s.PROCESS_STATUS, s.LAST_PROCESS_ATTEMPT_ID, s.COVERAGE_GAPS, s.RECONCILIATION_OK,
    s.UPDATED_AT
)
"""


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def write_successful_batch_fact(
    session: Any, projection: BatchProjection, process_attempt_id: str,
    curated_at: datetime,
) -> None:
    """Use the immutable RAW receipt to record one completed batch attempt.

    The caller owns the model transaction. A receipt or existing-key conflict
    aborts the transaction rather than silently replacing source audit values.
    """
    if not process_attempt_id or curated_at.tzinfo is None:
        raise ValueError("process attempt ID and aware curation time are required")
    receipts = session.sql(RECEIPT_SQL, params=[projection.attempt_id]).collect()
    if len(receipts) != 1:
        raise ValueError("expected exactly one immutable RAW load receipt")
    receipt = receipts[0].as_dict()
    counts = (receipt["SOURCE_ROWS_RETURNED"], receipt["RAW_ROWS_WRITTEN"],
              receipt["LOADED_ROWS"], projection.loaded_rows, projection.processed_rows)
    gaps = receipt["COVERAGE_GAPS"]
    if isinstance(gaps, str):
        gaps = json.loads(gaps)
    if (receipt["EXTRACT_STATUS"], receipt["LOAD_STATUS"]) != ("complete", "complete") \
            or len(set(counts)) != 1 or gaps not in (None, []):
        raise ValueError("RAW receipt is not complete and reconciled")
    fetched_at = receipt["FETCHED_AT"]
    if fetched_at is not None and (fetched_at.tzinfo is None or curated_at < fetched_at):
        raise ValueError("invalid fetch-to-curation time")
    prior = session.sql(EXISTING_SQL, params=[projection.attempt_id]).collect()
    if len(prior) > 1 or (prior and prior[0].as_dict()["LOGICAL_BATCH_ID"] !=
                           receipt["LOGICAL_BATCH_ID"]):
        raise ValueError("existing batch fact key conflicts with RAW receipt")
    row = {
        "attempt_id": projection.attempt_id,
        "logical_batch_id": receipt["LOGICAL_BATCH_ID"],
        "batch_kind": receipt["BATCH_KIND"],
        "site_key": receipt["SITE_KEY"],
        "requested_starttime": _iso(receipt["REQUESTED_STARTTIME"]),
        "requested_endtime": _iso(receipt["REQUESTED_ENDTIME"]),
        "fetched_at": _iso(fetched_at),
        "raw_recorded_at": _iso(receipt["RECORDED_AT"]),
        "curated_at": _iso(curated_at),
        "source_rows_returned": counts[0],
        "raw_rows_written": counts[1],
        "loaded_rows": counts[2],
        "processed_rows": projection.processed_rows,
        "rejected_rows": projection.rejected_rows,
        "fetch_to_curated_seconds": round((curated_at - fetched_at).total_seconds(), 3)
        if fetched_at is not None else None,
        "extract_status": receipt["EXTRACT_STATUS"],
        "load_status": receipt["LOAD_STATUS"],
        "process_status": "complete",
        "last_process_attempt_id": process_attempt_id,
        "coverage_gaps": gaps,
        "reconciliation_ok": True,
    }
    session.sql(MERGE_SQL, params=[json.dumps([row], separators=(",", ":"))]).collect()
