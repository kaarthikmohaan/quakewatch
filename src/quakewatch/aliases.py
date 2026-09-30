"""Group USGS preferred and associated IDs before revision deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AliasObservation:
    source_event_id: str
    associated_ids: tuple[str, ...] = ()


def canonical_id_map(observations: Iterable[AliasObservation]) -> dict[str, str]:
    """Map every linked source ID to one deterministic component ID.

    The alphabetically first exact ID in each connected component is the
    representative. This is recalculated from durable observations; a newly
    discovered alias can therefore require existing fact keys to be rekeyed.
    """
    parent: dict[str, str] = {}

    def find(event_id: str) -> str:
        parent.setdefault(event_id, event_id)
        root = event_id
        while parent[root] != root:
            root = parent[root]
        while parent[event_id] != event_id:
            next_id = parent[event_id]
            parent[event_id] = root
            event_id = next_id
        return root

    def join(first: str, second: str) -> None:
        left, right = find(first), find(second)
        if left != right:
            parent[max(left, right)] = min(left, right)

    for observation in observations:
        ids = (observation.source_event_id, *observation.associated_ids)
        if any(not isinstance(event_id, str) or not event_id.strip() for event_id in ids):
            raise ValueError("source and associated IDs must be non-empty strings")
        for associated_id in observation.associated_ids:
            join(observation.source_event_id, associated_id)
        find(observation.source_event_id)

    return {event_id: find(event_id) for event_id in sorted(parent)}
