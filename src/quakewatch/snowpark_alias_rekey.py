"""Move existing fact and bridge canonical keys inside the model transaction."""

from __future__ import annotations

from datetime import UTC
from typing import Any

from quakewatch.settings import SITES

FACT_KEYS_SQL = """
SELECT CANONICAL_EVENT_ID, SOURCE_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH,
       FETCHED_AT, STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER
FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION
"""

BRIDGE_KEYS_SQL = """
SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY
FROM QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE
"""

UPDATE_FACT_SQL = """
UPDATE QUAKEWATCH.CURATED.FACT_EVENT_REVISION
SET CANONICAL_EVENT_ID = ?
WHERE CANONICAL_EVENT_ID = ?
"""

UPDATE_BRIDGE_SQL = """
UPDATE QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE
SET CANONICAL_EVENT_ID = ?
WHERE CANONICAL_EVENT_ID = ?
"""

DELETE_FACT_SQL = """
DELETE FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION
WHERE CANONICAL_EVENT_ID = ? AND SOURCE_UPDATED_AT = TO_TIMESTAMP_TZ(?)
  AND PAYLOAD_HASH = ?
"""

DELETE_BRIDGE_SQL = """
DELETE FROM QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE
WHERE CANONICAL_EVENT_ID = ? AND SOURCE_UPDATED_AT = TO_TIMESTAMP_TZ(?)
  AND PAYLOAD_HASH = ?
"""


def _original_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row["CANONICAL_EVENT_ID"], row["SOURCE_UPDATED_AT"], row["PAYLOAD_HASH"])


def _rank(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row["FETCHED_AT"], row["STAGE_FILE_NAME"],
            row["STAGE_FILE_ROW_NUMBER"], row["CANONICAL_EVENT_ID"])


def _require_affected(session: Any, sql: str, params: list[Any], expected: int,
                      operation: str) -> None:
    results = session.sql(sql, params=params).collect()
    if len(results) != 1:
        raise ValueError(f"alias rekey {operation} returned no reliable row count")
    counts = {key.lower(): value for key, value in results[0].as_dict().items()}
    if counts.get(f"number of rows {operation}") != expected:
        raise ValueError(f"alias rekey {operation} count differs from preflight")


def rekey_existing_aliases(session: Any, canonical_ids: dict[str, str]) -> int:
    """Deduplicate alias collisions, then rekey facts and bridges atomically.

    A repeated logical revision keeps the latest fetched source row. Both the
    losing fact and its bridge rows are removed inside the caller's transaction.
    Any missing winner bridge or unexpected key stops before DML.
    """
    fact_rows = [row.as_dict() for row in session.sql(FACT_KEYS_SQL).collect()]
    old_to_new: dict[str, str] = {}
    original_facts: set[tuple[Any, ...]] = set()
    target_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in fact_rows:
        old = row["CANONICAL_EVENT_ID"]
        source_id = row["SOURCE_EVENT_ID"]
        new = canonical_ids.get(source_id)
        if not new:
            raise ValueError("existing revision source ID missing from durable alias map")
        if old in old_to_new and old_to_new[old] != new:
            raise ValueError("one existing canonical key maps to multiple alias groups")
        old_to_new[old] = new
        original = _original_key(row)
        if original in original_facts:
            raise ValueError("duplicate existing revision key before alias rekey")
        original_facts.add(original)
        target_groups.setdefault((new, row["SOURCE_UPDATED_AT"], row["PAYLOAD_HASH"]), []).append(row)

    moves = {old: new for old, new in old_to_new.items() if old != new}
    if not moves:
        return 0
    losers: set[tuple[Any, ...]] = set()
    collision_winners: set[tuple[Any, ...]] = set()
    for group in target_groups.values():
        if len(group) > 1:
            winner = max(group, key=_rank)
            collision_winners.add(_original_key(winner))
            losers.update(_original_key(row) for row in group if row is not winner)

    bridge_rows = [row.as_dict() for row in session.sql(BRIDGE_KEYS_SQL).collect()]
    target_bridges: set[tuple[Any, ...]] = set()
    original_bridges: set[tuple[Any, ...]] = set()
    bridge_counts: dict[tuple[Any, ...], int] = {}
    winner_sites: dict[tuple[Any, ...], set[str]] = {key: set() for key in collision_winners}
    for row in bridge_rows:
        old = row["CANONICAL_EVENT_ID"]
        original = _original_key(row)
        if original not in original_facts:
            raise ValueError("event-site bridge has no matching revision key")
        bridge_key = (*original, row["SITE_KEY"])
        if bridge_key in original_bridges:
            raise ValueError("duplicate existing event-site bridge key")
        original_bridges.add(bridge_key)
        bridge_counts[original] = bridge_counts.get(original, 0) + 1
        if original in losers:
            continue
        if original in winner_sites:
            winner_sites[original].add(row["SITE_KEY"])
        key = (old_to_new[old], row["SOURCE_UPDATED_AT"], row["PAYLOAD_HASH"],
               row["SITE_KEY"])
        if key in target_bridges:
            raise ValueError("alias rekey would collide with an existing bridge key")
        target_bridges.add(key)
    if any(sites != set(SITES) for sites in winner_sites.values()):
        raise ValueError("collision survivor lacks complete public-site bridge")
    fact_update_counts: dict[str, int] = {}
    bridge_update_counts: dict[str, int] = {}
    for row in fact_rows:
        original = _original_key(row)
        if original not in losers:
            old = row["CANONICAL_EVENT_ID"]
            fact_update_counts[old] = fact_update_counts.get(old, 0) + 1
            bridge_update_counts[old] = bridge_update_counts.get(old, 0) + bridge_counts.get(original, 0)
    for old, updated_at, payload_hash in sorted(losers):
        params = [old, updated_at.astimezone(UTC).isoformat(), payload_hash]
        _require_affected(session, DELETE_BRIDGE_SQL, params,
                          bridge_counts.get((old, updated_at, payload_hash), 0), "deleted")
        _require_affected(session, DELETE_FACT_SQL, params, 1, "deleted")
    for old, new in sorted(moves.items()):
        _require_affected(session, UPDATE_FACT_SQL, [new, old],
                          fact_update_counts.get(old, 0), "updated")
        _require_affected(session, UPDATE_BRIDGE_SQL, [new, old],
                          bridge_update_counts.get(old, 0), "updated")
    return len(moves)
