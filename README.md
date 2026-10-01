# QuakeWatch

QuakeWatch is a compact Snowflake batch warehouse for studying historical USGS earthquake records near public example locations. It preserves source revisions and records the time each batch was fetched so results can be audited and replayed.

This is a retrospective data project. It is not an earthquake warning, risk score, shaking estimate, or damage assessment. Distance and magnitude alone do not estimate impact.

## Status

The Python 3.12 environment and bounded USGS extractor are in place. The loader reported 177 of 180 planned history windows loaded and reconciled into Snowflake RAW, totaling 216,361 history rows; three history windows remain explicit USGS source gaps. All 177 loaded history attempts passed guarded Snowpark processing; 216,361 RAW rows were processed and 485 were rejected by typed projection. A separate 15-row Seattle sample was also processed by the warehouse procedure. Phase 2 revision, old-event update, tombstone, and rerun fixtures passed in an isolated database. Phase 3's initial uniqueness and health checks passed; aggregate post-run checks and reject-reason review remain. The catalog-wide update sweep remains incomplete because a bounded source request times out; its watermark has not advanced. CI and broader quality evidence are in progress. See [observed results](docs/results.md) for the evidence and its limits.

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
  -> raw VARIANT records (loaded) -> Snowpark warehouse models (15-row pilot and isolated fixtures verified)
```

The source returns bounded query results. QuakeWatch is a batch pipeline, not a streaming pipeline. USGS does not promise a transactionally consistent catalog snapshot, so the project will report unreconciled windows as coverage gaps rather than claim complete history.

## Docs

- [Design and project plan](docs/design.md)
- [Data dictionary](docs/data-dictionary.md)
- [Runbook](docs/runbook.md)
- [Phase 0 environment check](docs/environment.md)
- [Observed results](docs/results.md)

## Source and responsible use

Earthquake records come from the U.S. Geological Survey. Credit USGS and link to official records when presenting data. Use public example coordinates only. QuakeWatch must not be used for safety decisions.
