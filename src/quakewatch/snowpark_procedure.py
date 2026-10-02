"""Snowflake Python procedure entry point for one loaded RAW attempt."""

from __future__ import annotations

import json
from typing import Any

from quakewatch.process_transaction import process_loaded_attempt
from quakewatch.snowpark_alias_read import resolve_durable_aliases
from quakewatch.snowpark_model_writer import SnowparkModelWriter


def run(session: Any, attempt_id: str) -> str:
    """Transform one complete load; return its committed audit summary as JSON.

    Snowflake supplies the Snowpark session as the first handler argument.
    The coordinator records failures and raises them to the caller; only a
    committed successful outcome reaches the JSON response below.
    """
    outcome = process_loaded_attempt(
        session, attempt_id, SnowparkModelWriter(resolve_durable_aliases)
    )
    return json.dumps(
        {
            "process_attempt_id": outcome.process_attempt_id,
            "attempt_id": outcome.attempt_id,
            "status": outcome.status,
            "loaded_rows": outcome.loaded_rows,
            "processed_rows": outcome.processed_rows,
            "rejected_rows": outcome.rejected_rows,
            "revision_rows_merged": outcome.revision_rows_merged,
            "staging_parser_version": outcome.staging_parser_version,
        },
        separators=(",", ":"),
    )
