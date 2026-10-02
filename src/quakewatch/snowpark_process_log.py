"""Append one Snowpark processing outcome without replacing earlier attempts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from quakewatch.process_transaction import ProcessOutcome

EXISTING_SQL = """
SELECT PROCESS_ATTEMPT_ID
FROM QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT
WHERE PROCESS_ATTEMPT_ID = ?
"""

INSERT_SQL = """
INSERT INTO QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT (
    PROCESS_ATTEMPT_ID, ATTEMPT_ID, STARTED_AT, FINISHED_AT, STATUS,
    STAGING_PARSER_VERSION, LOADED_ROWS, PROCESSED_ROWS, REJECTED_ROWS,
    REVISION_ROWS_MERGED, ERROR_TYPE, ERROR_MESSAGE
)
SELECT f.value:process_attempt_id::VARCHAR,
       f.value:attempt_id::VARCHAR,
       TO_TIMESTAMP_TZ(f.value:started_at::VARCHAR),
       TO_TIMESTAMP_TZ(f.value:finished_at::VARCHAR),
       f.value:status::VARCHAR,
       f.value:staging_parser_version::VARCHAR,
       f.value:loaded_rows::NUMBER(38, 0),
       f.value:processed_rows::NUMBER(38, 0),
       f.value:rejected_rows::NUMBER(38, 0),
       f.value:revision_rows_merged::NUMBER(38, 0),
       f.value:error_type::VARCHAR,
       f.value:error_message::VARCHAR
FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f
"""


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def append_process_outcome(session: Any, outcome: ProcessOutcome) -> None:
    """Insert a success inside the model transaction or failure after rollback.

    The caller controls that boundary. Duplicate process IDs stop rather than
    overwrite an earlier outcome; a fresh retry must use a fresh ID.
    """
    if not outcome.process_attempt_id or not outcome.attempt_id:
        raise ValueError("process and load attempt IDs are required")
    if outcome.status not in ("complete", "failed"):
        raise ValueError("invalid processing status")
    if (outcome.started_at.tzinfo is None or outcome.finished_at.tzinfo is None
            or outcome.finished_at < outcome.started_at):
        raise ValueError("processing times must be ordered and timezone-aware")
    counts = (outcome.loaded_rows, outcome.processed_rows,
              outcome.rejected_rows, outcome.revision_rows_merged)
    if any(not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError("processing counts must be nonnegative integers")
    if outcome.processed_rows > outcome.loaded_rows or outcome.rejected_rows > outcome.processed_rows:
        raise ValueError("processing counts are inconsistent")
    if outcome.status == "complete" and (outcome.error_type or outcome.error_message):
        raise ValueError("successful processing cannot carry an error")
    if outcome.status == "failed" and (not outcome.error_type or outcome.revision_rows_merged):
        raise ValueError("failed processing needs an error and zero committed revisions")
    if session.sql(EXISTING_SQL, params=[outcome.process_attempt_id]).collect():
        raise ValueError("processing attempt ID already recorded")
    row = {
        "process_attempt_id": outcome.process_attempt_id,
        "attempt_id": outcome.attempt_id,
        "started_at": _iso(outcome.started_at),
        "finished_at": _iso(outcome.finished_at),
        "status": outcome.status,
        "staging_parser_version": outcome.staging_parser_version,
        "loaded_rows": outcome.loaded_rows,
        "processed_rows": outcome.processed_rows,
        "rejected_rows": outcome.rejected_rows,
        "revision_rows_merged": outcome.revision_rows_merged,
        "error_type": outcome.error_type,
        "error_message": outcome.error_message,
    }
    session.sql(INSERT_SQL, params=[json.dumps([row], separators=(",", ":"))]).collect()
