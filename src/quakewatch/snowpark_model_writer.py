"""Connect local model writers to the in-Snowflake transaction coordinator."""

from __future__ import annotations

from typing import Any, Callable

from quakewatch.process_batch import BatchProjection
from quakewatch.process_transaction import ProcessOutcome
from quakewatch.snowpark_alias_rekey import rekey_existing_aliases
from quakewatch.snowpark_batch_fact_write import write_successful_batch_fact
from quakewatch.snowpark_dimensions_write import write_dimensions_and_bridge
from quakewatch.snowpark_process_log import append_process_outcome
from quakewatch.snowpark_revision_write import write_revision_fact
from quakewatch.snowpark_staging_write import write_staging


CanonicalResolver = Callable[[Any, BatchProjection], dict[str, str]]


class SnowparkModelWriter:
    """Run model DML in order; the coordinator owns BEGIN/COMMIT/ROLLBACK.

    The resolver must use durable alias observations. Rekey collisions stop
    before model writes; the coordinator rolls back the staging transaction.
    """

    def __init__(self, canonical_resolver: CanonicalResolver):
        self.canonical_resolver = canonical_resolver
        self._projection: BatchProjection | None = None

    def write_models(self, session: Any, projection: BatchProjection) -> int:
        write_staging(session, projection)
        canonical_ids = self.canonical_resolver(session, projection)
        rekey_existing_aliases(session, canonical_ids)
        merged = write_revision_fact(session, projection, canonical_ids)
        write_dimensions_and_bridge(session, projection, canonical_ids)
        self._projection = projection
        return merged

    def record_success(self, session: Any, outcome: ProcessOutcome) -> None:
        if self._projection is None or self._projection.attempt_id != outcome.attempt_id:
            raise ValueError("successful outcome lacks its completed model projection")
        write_successful_batch_fact(
            session, self._projection, outcome.process_attempt_id, outcome.finished_at
        )
        append_process_outcome(session, outcome)
        self._projection = None

    def record_failure(self, session: Any, outcome: ProcessOutcome) -> None:
        self._projection = None
        append_process_outcome(session, outcome)
