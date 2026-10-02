# ADR 0002: Revision identity and append-only history

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026

## Context

USGS revises magnitude, location, and status after an event. Overlapping or repeated batches return the same revision more than once, and two different payloads can share an update time.

## Decision

Identify a revision by `(canonical_event_id, source_updated_at, payload_hash)`. Keep every distinct revision in `FACT_EVENT_REVISION` instead of overwriting one row, deduplicate candidates before each `MERGE`, and choose the current revision in a view ranked by update time, then fetch time and fixed tie-breakers.

## Consequences

- Reruns and overlapping batches converge to the same facts.
- History supports "what changed and when" questions.
- The fact table grows with every revision; current state needs the ranking view.

**References:** [revisions.py](../../src/quakewatch/revisions.py), [revision DDL](../../sql/setup/07_revision_current.sql)
