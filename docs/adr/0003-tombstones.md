# ADR 0003: Deletions are kept as tombstones

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026

## Context

USGS marks deleted events with a `deleted` status rather than removing them. An older batch replayed later can still contain the event as active.

## Decision

Store a deletion as the latest revision with `deleted` status. `EVENT_CURRENT` ranks all revisions first and hides an event only when its latest revision is deleted. Absence from a response is never treated as deletion.

## Consequences

- A stale replay cannot bring back a deleted event; this is covered by a fixture test and an isolated Snowflake drill.
- Filtering deleted rows before ranking would be wrong, which the view's comment records.

**References:** [EVENT_CURRENT view](../../sql/phase2_revision_current.sql)
