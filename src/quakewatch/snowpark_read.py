"""Read a complete RAW attempt from Snowflake inside the Snowpark procedure."""

from __future__ import annotations

import json
from typing import Any

from quakewatch.process_batch import BatchProjection, RawObservation, project_raw_attempt

RECEIPT_SQL = """
SELECT ATTEMPT_ID, EXTRACT_STATUS, LOAD_STATUS, COVERAGE_GAPS,
       SOURCE_ROWS_RETURNED, RAW_ROWS_WRITTEN, LOADED_ROWS
FROM QUAKEWATCH.RAW.BATCH_ATTEMPT
WHERE ATTEMPT_ID = ?
"""

RAW_SQL = """
SELECT ATTEMPT_ID, WINDOW_ID, STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER,
       FETCHED_AT, PAYLOAD_HASH, PARSER_VERSION, PAYLOAD
FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS
WHERE ATTEMPT_ID = ?
ORDER BY STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER
"""


def _variant(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def read_and_project_attempt(session: Any, attempt_id: str) -> BatchProjection:
    """Read only one verified complete load and project its RAW observations.

    ``session`` is the Snowpark Session supplied inside the Python procedure.
    The local fixture tests use a fake session, so Snowpark is not imported on
    the Apple Silicon development machine.
    """
    if not attempt_id:
        raise ValueError("attempt ID is required")
    receipts = [row.as_dict() for row in session.sql(RECEIPT_SQL, params=[attempt_id]).collect()]
    if len(receipts) != 1:
        raise ValueError("expected exactly one immutable RAW load receipt")
    receipt = receipts[0]
    if receipt["EXTRACT_STATUS"] != "complete" or receipt["LOAD_STATUS"] != "complete":
        raise ValueError("RAW load receipt is not complete")
    if _variant(receipt["COVERAGE_GAPS"]) not in (None, []):
        raise ValueError("RAW load receipt has unresolved coverage gaps")
    loaded = receipt["LOADED_ROWS"]
    if (
        not isinstance(loaded, int)
        or loaded < 0
        or any(receipt[name] != loaded for name in ("SOURCE_ROWS_RETURNED", "RAW_ROWS_WRITTEN"))
    ):
        raise ValueError("RAW load receipt counts do not reconcile")

    rows = []
    for result in session.sql(RAW_SQL, params=[attempt_id]).collect():
        row = result.as_dict()
        rows.append(
            RawObservation(
                attempt_id=row["ATTEMPT_ID"],
                window_id=row["WINDOW_ID"],
                stage_file_name=row["STAGE_FILE_NAME"],
                stage_file_row_number=row["STAGE_FILE_ROW_NUMBER"],
                fetched_at=row["FETCHED_AT"],
                payload_hash=row["PAYLOAD_HASH"],
                raw_parser_version=row["PARSER_VERSION"],
                payload=_variant(row["PAYLOAD"]),
            )
        )
    return project_raw_attempt(rows, attempt_id, loaded)
