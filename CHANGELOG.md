# Changelog

Notable changes to QuakeWatch. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Measured results and their evidence
are in the [results summary](docs/results.md).

## [Unreleased]

### Changed

- README next steps now link to the v0.2.0 milestone issues.

## [0.1.0] - 2026-10-02

The first complete version of the batch path: extraction, loading, modeling,
quality checks, and recovery, verified end to end on 2 October 2026.

### Added

- **Extraction:** bounded, count-checked USGS FDSN requests with retries, a
  shared per-window deadline, recursive window splitting, child checkpoints, and
  a manifest for every attempt.
- **RAW loading:** internal stage and `COPY INTO` with full-payload `VARIANT`
  rows, reconciled against local counts, and an append-only `BATCH_ATTEMPT`
  receipt per attempt.
- **Modeling:** a Snowpark procedure that builds typed staging with recorded
  rejects, append-only revision history, tombstones, alias resolution,
  event-to-site distances, dimensions, and batch facts in one transaction per
  batch.
- **Quality checks:** reconciliation, uniqueness, health views, latency
  measurement against a target set in advance, and analysis queries.
- **Update sweep:** a catalog-wide `updatedafter` sweep whose watermark lives in
  Snowflake and advances by compare-and-set only after full reconciliation.
- **Recovery drills:** failed-transform retry from RAW, and clone and Time Travel
  recovery on an isolated fixture database.
- **Optional Cortex briefs:** factual summaries of SQL aggregates, checked
  against the SQL facts with a SQL fallback.
- **Live integration check:** compiles every procedure and reviewed SQL statement
  against Snowflake with `EXPLAIN`, plus read-only checks; runs from a manual
  GitHub workflow.
- **Tooling:** a Makefile, ruff lint and format checks, mypy, coverage with an
  80% minimum, structured UTC logging, and Dependabot.
- **Documentation:** README with key results and an architecture diagram, data
  dictionary and ERD, ten architecture decision records, an operations
  reference, an evidence log, and community files.

### Changed

- Staging parser version 2 labels USGS placeholder records as
  `source_stub_record` instead of `invalid_origin_time`, and rejects active
  records at the `[0, 0]` placeholder; the 485 stored rejects were relabelled in
  one checked transaction.
- Files are named by purpose instead of build phase.

### Fixed

- A terminated capture is now recorded as `failed` instead of staying `running`.
- HTTP client request logs no longer flood command output.

### Known limitations

- History windows 12, 42, and 73 are USGS source gaps.
- The catalog-wide update sweep has not completed, so no watermark has been
  committed.
- Fetch-to-curated latency was measured only on a manually run backfill (p95
  35.9 hours against a 24-hour target).
- No target analyst has tested the comparison task yet.

[Unreleased]: https://github.com/kaarthikmohaan/quakewatch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kaarthikmohaan/quakewatch/releases/tag/v0.1.0
