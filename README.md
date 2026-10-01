# QuakeWatch

[![CI](https://github.com/kaarthikmohaan/quakewatch/actions/workflows/ci.yml/badge.svg)](https://github.com/kaarthikmohaan/quakewatch/actions/workflows/ci.yml)

QuakeWatch is a compact Snowflake batch warehouse for studying historical USGS earthquake records near public example locations. It preserves source revisions and records the time each batch was fetched so results can be audited and replayed.

This is a retrospective data project. It is not an earthquake warning, risk score, shaking estimate, or damage assessment. Distance and magnitude alone do not estimate impact.

## Status

The Python 3.12 environment and bounded USGS extractor are in place. The loader reported 177 of 180 planned history windows loaded and reconciled into Snowflake RAW, totaling 216,361 history rows; windows 12, 42, and 73 remain explicit USGS source gaps. All 177 loaded history attempts passed guarded Snowpark processing; 216,361 RAW rows were processed and 485 were rejected as `invalid_origin_time`. A separate overlapping 15-row Seattle sample was also processed. Phase 2 revision, old-event update, tombstone, rerun, and failed-transform/retry fixtures passed in an isolated database. Phase 3's post-run checks found all 178 receipts reconciled, with zero loaded-window anomalies or duplicate revision/bridge keys. Its 178-attempt first-backfill sample missed the predeclared 24-hour p95 fetch-to-curated target (35.9 hours observed).

The optional Phase 4 fixture-table clone and Time Travel drill passed, and the demo clone was dropped. A later bounded Cortex evaluation produced nine human-reviewed factual briefs from saved SQL aggregates; one owner comparison preferred the brief for scanning. The eleven completed Cortex calls consumed 0.003948756 measured AI credits, separate from warehouse compute. The catalog-wide update sweep remains incomplete because a bounded source request times out; its watermark has not advanced. The owner stopped further USGS source retries on 1 October 2026. Secret-free GitHub CI passed at pushed commit `d4ceb9f`; newer local commits have not been pushed or checked by GitHub Actions. See [observed results](docs/results.md), the [Cortex evaluation](docs/phase4-cortex-evaluation.md), and the [Phase 4 close-out](docs/phase4-closeout.md) for evidence and limits.

The Phase 4 metering snapshot reports actual shared warehouse-hour credits,
with lag and attribution limits; it is not a per-demo bill.

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
