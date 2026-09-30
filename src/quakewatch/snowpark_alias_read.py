"""Resolve canonical IDs from all durable, accepted staging observations."""

from __future__ import annotations

import json
from typing import Any

from quakewatch.aliases import AliasObservation, canonical_id_map
from quakewatch.process_batch import BatchProjection


ALIAS_OBSERVATIONS_SQL = """
SELECT SOURCE_EVENT_ID, ASSOCIATED_IDS
FROM QUAKEWATCH.CURATED.STG_EVENT_REVISION
WHERE REJECT_REASON IS NULL
  AND SOURCE_EVENT_ID IS NOT NULL
"""


def _ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("durable associated IDs must be an array of non-empty strings")
    return tuple(value)


def resolve_durable_aliases(session: Any, projection: BatchProjection) -> dict[str, str]:
    """Build one map from staging history, including the just-written batch.

    The model adapter calls this after its staging MERGE and within the same
    transaction. Prior batches and current valid observations both contribute.
    """
    observations = [
        AliasObservation(row.as_dict()["SOURCE_EVENT_ID"],
                         _ids(row.as_dict()["ASSOCIATED_IDS"]))
        for row in session.sql(ALIAS_OBSERVATIONS_SQL).collect()
    ]
    mapping = canonical_id_map(observations)
    for item in projection.observations:
        if item.fields["reject_reason"] is None and item.fields["source_event_id"] not in mapping:
            raise ValueError("current accepted event missing from durable alias observations")
    return mapping
