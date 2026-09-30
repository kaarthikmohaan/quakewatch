"""Move existing fact and bridge canonical keys inside the model transaction."""

from __future__ import annotations

from typing import Any


FACT_KEYS_SQL = """
SELECT CANONICAL_EVENT_ID, SOURCE_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
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


def rekey_existing_aliases(session: Any, canonical_ids: dict[str, str]) -> int:
    """Rekey existing revisions and bridges after checking every target key.

    Any revision or bridge collision stops before a write. Collision merging
    needs a separate deduplication step; silently changing keys would violate
    the declared grains. The caller owns the transaction and rollback.
    """
    fact_rows = [row.as_dict() for row in session.sql(FACT_KEYS_SQL).collect()]
    old_to_new: dict[str, str] = {}
    target_facts: set[tuple[Any, ...]] = set()
    for row in fact_rows:
        old = row["CANONICAL_EVENT_ID"]
        source_id = row["SOURCE_EVENT_ID"]
        new = canonical_ids.get(source_id)
        if not new:
            raise ValueError("existing revision source ID missing from durable alias map")
        if old in old_to_new and old_to_new[old] != new:
            raise ValueError("one existing canonical key maps to multiple alias groups")
        old_to_new[old] = new
        key = (new, row["SOURCE_UPDATED_AT"], row["PAYLOAD_HASH"])
        if key in target_facts:
            raise ValueError("alias rekey would collide with an existing revision key")
        target_facts.add(key)

    moves = {old: new for old, new in old_to_new.items() if old != new}
    if not moves:
        return 0
    bridge_rows = [row.as_dict() for row in session.sql(BRIDGE_KEYS_SQL).collect()]
    target_bridges: set[tuple[Any, ...]] = set()
    for row in bridge_rows:
        old = row["CANONICAL_EVENT_ID"]
        if old not in old_to_new:
            raise ValueError("event-site bridge has no matching revision canonical key")
        key = (old_to_new[old], row["SOURCE_UPDATED_AT"], row["PAYLOAD_HASH"],
               row["SITE_KEY"])
        if key in target_bridges:
            raise ValueError("alias rekey would collide with an existing bridge key")
        target_bridges.add(key)
    for old, new in sorted(moves.items()):
        session.sql(UPDATE_FACT_SQL, params=[new, old]).collect()
        session.sql(UPDATE_BRIDGE_SQL, params=[new, old]).collect()
    return len(moves)
