"""Transaction boundary for an in-Snowflake batch transformation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from quakewatch.process_batch import BatchProjection
from quakewatch.snowpark_read import read_and_project_attempt
from quakewatch.staging import STAGING_PARSER_VERSION


@dataclass(frozen=True)
class ProcessOutcome:
    process_attempt_id: str
    attempt_id: str
    started_at: datetime
    finished_at: datetime
    status: str
    loaded_rows: int
    processed_rows: int
    rejected_rows: int
    revision_rows_merged: int
    error_type: str | None = None
    error_message: str | None = None
    staging_parser_version: str = STAGING_PARSER_VERSION


class ModelWriter(Protocol):
    """DML-only writer; the concrete Snowpark implementation comes later."""

    def write_models(self, session: Any, projection: BatchProjection) -> int: ...
    def record_success(self, session: Any, outcome: ProcessOutcome) -> None: ...
    def record_failure(self, session: Any, outcome: ProcessOutcome) -> None: ...


def process_loaded_attempt(
    session: Any,
    attempt_id: str,
    writer: ModelWriter,
    *,
    make_id: Callable[[], str] = lambda: uuid4().hex,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ProcessOutcome:
    """Read RAW, commit models plus success log, or roll back and log failure."""
    process_id = make_id()
    started_at = now()
    projection: BatchProjection | None = None
    in_transaction = False
    committing = False
    try:
        projection = read_and_project_attempt(session, attempt_id)
        session.sql("BEGIN TRANSACTION").collect()
        in_transaction = True
        merged = writer.write_models(session, projection)
        if not isinstance(merged, int) or merged < 0:
            raise ValueError("writer returned an invalid merged revision count")
        outcome = ProcessOutcome(
            process_attempt_id=process_id, attempt_id=attempt_id,
            started_at=started_at, finished_at=now(), status="complete",
            loaded_rows=projection.loaded_rows, processed_rows=projection.processed_rows,
            rejected_rows=projection.rejected_rows, revision_rows_merged=merged,
        )
        writer.record_success(session, outcome)
        committing = True
        session.sql("COMMIT").collect()
        return outcome
    except Exception as exc:
        if committing:
            # A failed COMMIT call can have an unknown outcome; do not write a
            # misleading failed record or retry automatically.
            raise RuntimeError("commit outcome unknown; inspect Snowflake before retry") from exc
        if in_transaction:
            try:
                session.sql("ROLLBACK").collect()
            except Exception as rollback_error:
                raise RuntimeError("rollback outcome unknown; inspect Snowflake before retry") from rollback_error
        failed = ProcessOutcome(
            process_attempt_id=process_id, attempt_id=attempt_id,
            started_at=started_at, finished_at=now(), status="failed",
            loaded_rows=projection.loaded_rows if projection else 0,
            processed_rows=projection.processed_rows if projection else 0,
            rejected_rows=projection.rejected_rows if projection else 0,
            revision_rows_merged=0,
            error_type=type(exc).__name__,
            error_message=str(exc) if isinstance(exc, ValueError) else "Transformation failed",
        )
        writer.record_failure(session, failed)
        raise
