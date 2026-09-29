# QuakeWatch

QuakeWatch is a compact Snowflake batch warehouse for studying historical USGS earthquake records near public example locations. It preserves source revisions and records the time each batch was fetched so results can be audited and replayed.

This is a retrospective data project. It is not an earthquake warning, risk score, shaking estimate, or damage assessment. Distance and magnitude alone do not estimate impact.

## Status

The Python 3.12 environment and bounded USGS extractor are in place. Three Seattle attempts have been loaded into Snowflake RAW: a reconciled 15-row day and reconciled 167-row and 185-row months. The five-year history and update sweep are still incomplete. Warehouse models and CI are not implemented yet.

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
  -> Snowflake internal stage and COPY INTO (three Seattle loads complete)
  -> raw VARIANT records (loaded) -> Snowpark warehouse models (planned)
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
