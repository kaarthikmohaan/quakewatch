# QuakeWatch

[![CI](https://github.com/kaarthikmohaan/quakewatch/actions/workflows/ci.yml/badge.svg)](https://github.com/kaarthikmohaan/quakewatch/actions/workflows/ci.yml)

QuakeWatch is a compact Snowflake batch warehouse for studying historical USGS earthquake records near public locations. It preserves source revisions and records the time each batch was fetched so results can be audited and replayed.

This is a retrospective data project. It is not an earthquake warning, risk score, shaking estimate, or damage assessment. Distance and magnitude alone do not estimate impact.

1. USGS extraction: A Python command fetches earthquake records for an explicit site and UTC time window. It saves the full GeoJSON records as JSONL, plus a manifest with query parameters, counts, and fetch status. The [extractor](https://github.com/kaarthikmohaan/quakewatch/blob/main/src/quakewatch/extract_batch.py) uses bounded requests so failed windows remain visible.

2. Snowflake loading: Python uploads the files to a Snowflake internal stage and uses COPY INTO to retain the source payload and batch metadata in RAW tables. The historical backfill loaded 177 of 180 planned windows, containing 216,361 source rows. Three windows remain USGS source gaps. See the [README](https://github.com/kaarthikmohaan/quakewatch/blob/main/README.md).

3. Warehouse modeling: A Snowpark procedure validates rows and builds revision history, a latest-current-event view, site distances, dimensions, and batch facts. It preserves updates and deletion records instead of simply overwriting an event. All 177 loaded history attempts were processed; 485 rows were rejected for invalid origin times. The [data dictionary](https://github.com/kaarthikmohaan/quakewatch/blob/main/docs/data-dictionary.md) lists the tables and their row grains.

4. Quality and recovery: The project has batch reconciliation, reject and health views, duplicate-key checks, and processing audits. Fixture runs verified reruns, old-event updates, deletions, rollback, and retry from existing RAW data. A separate Snowflake clone and Time Travel recovery drill passed. The [results](https://github.com/kaarthikmohaan/quakewatch/blob/main/docs/results.md) record the evidence.

5. Analysis and AI brief: SQL supports historical counts and magnitude comparisons around Seattle, San Francisco, and Anchorage. A Cortex evaluation generated nine human-checked factual briefs from saved SQL aggregates.

6. Engineering setup: The repo has a locked Python environment, unit and fixture tests, secret-free GitHub Actions CI, a [runbook](https://github.com/kaarthikmohaan/quakewatch/blob/main/docs/runbook.md), and a [demo](https://github.com/kaarthikmohaan/quakewatch/blob/main/docs/demo.md).

## Quickstart

From the repository root, use Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked --no-editable
uv run quakewatch-extract \
  --site seattle \
  --start 2026-09-28T00:00:00Z \
  --end 2026-09-29T00:00:00Z
```

This is a dated example. Change the site and UTC time range for a new batch;
supported sites are `seattle`, `san-francisco`, and `anchorage`. Each run prints
a new attempt ID and saves `events.jsonl` plus `manifest.json` under
`data/raw/<attempt-id>/`. The `data/` directory is excluded from Git.

To check a saved batch locally, replace `PASTE_ATTEMPT_ID_HERE` with the ID
printed by the extractor:

```sh
attempt_id=PASTE_ATTEMPT_ID_HERE
PYTHONPATH=src .venv/bin/python -m quakewatch.raw_load \
  "data/raw/$attempt_id/manifest.json"
```

That check prints the expected row count and Snowflake stage path. It does not
upload or process data. A live Snowflake load needs the configured project
connection and can use warehouse credits

## Architecture

```
USGS FDSN GeoJSON earthquake records
  -> Bounded Python requests for historical windows or later source updates
  -> events.jsonl (full records) + manifest.json (counts, times, gaps)
  -> Python loader -> Snowflake internal stage -> COPY INTO RAW_EVENT_RECORDS
  -> Snowpark procedure
       -> typed staging rows and recorded rejects
       -> event revision history -> latest non-deleted EVENT_CURRENT view
       -> event-to-site distances, dimensions, and batch audit facts
  -> SQL comparisons and health checks
       -> Cortex brief, checked against the SQL facts

Separate optional recovery drill: fixture-table clone -> test change
  -> Time Travel check -> remove the demo clone
GitHub Actions: local fixture tests without Snowflake credentials
```

Each batch keeps its source records and counts so a failed transformation can
retry from RAW without fetching again. The catalog-wide update sweep is still
incomplete, and three historical source windows remain gaps. QuakeWatch runs
bounded batches, not a continuous stream; USGS does not provide a consistent
snapshot of the whole catalog. Cortex and the recovery drill are optional and
do not change the regular batch path.

## Docs

- [Design and project plan](docs/design.md)
- [Data dictionary](docs/data-dictionary.md)
- [Runbook](docs/runbook.md)
- [Phase 0 environment check](docs/environment.md)
- [Observed results](docs/results.md)
- [Target-analyst interview guide](docs/target-user-interview.md)
- [Two-minute evidence-based demo](docs/demo.md)

## Source and responsible use

Earthquake records come from the U.S. Geological Survey. Credit USGS and link to official records when presenting data. Use public example coordinates only. QuakeWatch must not be used for safety decisions.
