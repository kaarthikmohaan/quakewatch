# QuakeWatch

[![CI](https://github.com/kaarthikmohaan/quakewatch/actions/workflows/ci.yml/badge.svg)](https://github.com/kaarthikmohaan/quakewatch/actions/workflows/ci.yml)

QuakeWatch is a compact Snowflake batch warehouse for studying historical USGS earthquake records near public locations. It preserves source revisions and records the time each batch was fetched so results can be audited and replayed.

This is a retrospective data project. It is not an earthquake warning, risk score, shaking estimate, or damage assessment. Distance and magnitude alone do not estimate impact.

1. USGS extraction: A Python command fetches earthquake records for an explicit site and UTC time window. It saves the full GeoJSON records as JSONL, plus a manifest with query parameters, counts, and fetch status. The [extractor](/Users/karthikmohan/Developer/quakewatch/src/quakewatch/extract_batch.py) uses bounded requests so failed windows remain visible.

2. Snowflake loading: Python uploads the files to a Snowflake internal stage and uses COPY INTO to retain the source payload and batch metadata in RAW tables. The historical backfill loaded 177 of 180 planned windows, containing 216,361 source rows. Three windows remain USGS source gaps. See the [README](/Users/karthikmohan/Developer/quakewatch/README.md).

3. Warehouse modeling: A Snowpark procedure validates rows and builds revision history, a latest-current-event view, site distances, dimensions, and batch facts. It preserves updates and deletion records instead of simply overwriting an event. All 177 loaded history attempts were processed; 485 rows were rejected for invalid origin times. The [data dictionary](/Users/karthikmohan/Developer/quakewatch/docs/data-dictionary.md) lists the tables and their row grains.

4. Quality and recovery: The project has batch reconciliation, reject and health views, duplicate-key checks, and processing audits. Fixture runs verified reruns, old-event updates, deletions, rollback, and retry from existing RAW data. A separate Snowflake clone and Time Travel recovery drill passed. The [results](/Users/karthikmohan/Developer/quakewatch/docs/results.md) record the evidence.

5. Analysis and optional AI brief: SQL supports historical counts and magnitude comparisons around Seattle, San Francisco, and Anchorage. A Cortex evaluation generated nine human-checked factual briefs from saved SQL aggregates.

6. Engineering setup: The repo has a locked Python environment, unit and fixture tests, secret-free GitHub Actions CI, a [runbook](/Users/karthikmohan/Developer/quakewatch/docs/runbook.md), and a [demo](/Users/karthikmohan/Developer/quakewatch/docs/demo.md).

## Quickstart

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked --no-editable
uv run quakewatch-extract \
  --site seattle \
  --start 2026-09-28T00:00:00Z \
  --end 2026-09-29T00:00:00Z
```

The command requires an explicit location and time range. It writes `events.jsonl` and `manifest.json` under `data/raw/<attempt-id>/`; `data/` is excluded from Git. See [the runbook](docs/runbook.md) for more details.

## Architecture

```text
USGS FDSN GeoJSON
  -> Python bounded batch extractor
  -> JSON Lines + query-count manifest
  -> Snowflake internal stage and COPY INTO (177 history windows loader-reported complete)
  -> raw VARIANT records (loaded) -> Snowpark warehouse models (177 history attempts processed)
```

The source returns bounded query results. QuakeWatch is a batch pipeline, not a streaming pipeline. USGS does not promise a transactionally consistent catalog snapshot, so the project will report unreconciled windows as coverage gaps rather than claim complete history.

## Docs

- [Design and project plan](docs/design.md)
- [Data dictionary](docs/data-dictionary.md)
- [Runbook](docs/runbook.md)
- [Phase 0 environment check](docs/environment.md)
- [Observed results](docs/results.md)
- [Phase 4 close-out and remaining work](docs/phase4-closeout.md)
- [Target-analyst interview guide](docs/target-user-interview.md)
- [Two-minute evidence-based demo](docs/demo.md)

## Source and responsible use

Earthquake records come from the U.S. Geological Survey. Credit USGS and link to official records when presenting data. Use public example coordinates only. QuakeWatch must not be used for safety decisions.
