# QuakeWatch: USGS Earthquake Data Warehouse

**Project document · 29 September 2026 · Planning baseline**

> A compact batch data warehouse for analyzing USGS earthquake records and revisions across public example locations. QuakeWatch is retrospective analysis, not an earthquake warning, risk score, or damage assessment. Distance and magnitude alone do not estimate shaking or impact.

**Status (updated 2 October 2026):** this page is the frozen planning baseline written before implementation. Its plan, targets, and estimates are unchanged below. The batch path has since been built and measured; see the [results summary](results.md) for what was met, missed, and still open, and the checklist at the end of this page for a quick view.

### Run the current extractor

Python 3.12 and `uv` are required. From this repository directory:

```sh
uv sync --locked --no-editable
uv run quakewatch-extract \
  --site seattle \
  --start 2026-09-28T00:00:00Z \
  --end 2026-09-29T00:00:00Z
```

The command requires an explicit site and UTC time range so it cannot accidentally launch the full five-year history load. It saves `events.jsonl` and a `manifest.json` under `data/raw/<attempt-id>/`; `data/` is ignored by Git. `--no-editable` installs the package as a small local wheel because the editable install path was not loading correctly in this environment. After changing package code, run `uv sync --locked --no-editable` again.

## Problem and goal

A facilities or community-preparedness analyst wants to compare historical USGS earthquake records around three public example sites. Today they scan USGS maps or download records manually. QuakeWatch loads source records in bounded batches, preserves revisions, and provides reproducible comparisons in Snowflake.

The warehouse can answer:

- How do event counts and magnitude distributions change over time within a configured radius of each example site?
- Which event records were revised or deleted, and when did the warehouse observe those changes?
- How much time passed between source update, batch fetch, and curated availability?
- Which requested time windows have not been loaded successfully?

Distance and magnitude are descriptive filters only. The project does not estimate shaking, risk, damage, or recommended action.

**Target user:** a facilities-planning analyst comparing historical event records around candidate sites. Seattle, San Francisco, and Anchorage are public demonstration locations only; the user interview must confirm that cross-site comparisons are useful. The planning baseline uses public city-center coordinates, a 250 km radius, and a rolling five-year event-time window, all stored in example configuration. USGS maps and notifications remain strong alternatives.

### Scope

| In scope | Out of scope |
|---|---|
| Manually invoked bounded batch extracts from USGS FDSN GeoJSON | Claims of a continuous stream, warning, prediction, risk score, shaking, or damage |
| Historical comparisons around Seattle, San Francisco, and Anchorage, within 250 km and over a five-year event-time window | Private coordinates in Git or public demo outputs |
| Revision-aware historical facts, curated dimensions, and analytical views | Guaranteed complete coverage without audited source ranges |
| Reproducible backfills, idempotent loads, quality checks, and run evidence | Production uptime or a production SLO |
| Snowflake batch warehouse with Python extraction and Snowpark transformations | Snowpipe Streaming, Kafka, Spark, or a second cloud warehouse |

### Definition of success

These are acceptance targets, not achieved results:

- Each ingestion batch records its requested time range, query parameters, count-before/count-after values, row counts, fetch time, outcome, and any incomplete window.
- Raw data preserves the full source record and request/batch metadata.
- Re-running an identical batch does not create duplicate logical event revisions or change aggregate counts.
- A revision or deletion to an old event outside the recent origin-time window is found by the update sweep, creates a historical revision or tombstone, and updates the current-event view.
- A deleted event is retained as a tombstone; an older backfill cannot resurrect it.
- A failed transform can be retried from already loaded raw data without refetching the API.
- The `updatedafter` watermark advances only after every bounded query window is loaded and reconciled; incomplete sweeps remain retryable.
- Fact and dimension grains, keys, and joins are documented and checked with SQL.
- Report requested/loaded/rejected rows, pending batches, coverage gaps, source age, and fetch-to-curated latency separately.
- Set a sample period and target before measurement; publish observed results and sample size, not targets as results.
- Before expanding beyond the thin slice, ask one facilities-planning analyst to complete a five-year site/magnitude comparison and review its revisions and coverage notes. Record the manual baseline and actual task time; set any improvement target before comparing. Continue with this product framing only if the user confirms the task is useful.

## Batch architecture and roadmap

The source API returns bounded query results. One Python batch-runner command performs extraction, writes JSONL files and an attempt manifest, uploads them to a Snowflake internal stage, runs `COPY INTO`, reconciles load counts, and invokes the Snowpark transformation procedure through the Snowflake Python Connector. The initial historical load covers the five-year event-time horizon around the example sites. Later runs use an `updatedafter` sweep from the configured USGS catalog lower bound, without spatial or magnitude filters, so revisions and deletions to old events are captured even when an event moves across a site boundary. The warehouse keeps updates for events within the five-year horizon or already present in current state.

**Runtime boundary:** use Python 3.12 for the local HTTPX/Connector batch runner, and run Snowpark only inside the Snowflake Python procedure. Before implementation, query `SNOWFLAKE.INFORMATION_SCHEMA.PACKAGES` for the account's available Python runtimes and Snowpark versions, then pin the procedure runtime/package and local Connector versions. Snowflake currently lists Python 3.12 as generally available; its Snowpark setup guide also documents a local Snowpark/PyOpenSSL issue on Apple M1. This design avoids local Snowpark imports; if local Snowpark use is added, test it separately on the actual Mac architecture. [Snowpark runtime guidance](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup), [package catalog](https://docs.snowflake.com/en/sql-reference/info-schema/packages).

    USGS FDSN GeoJSON API
      -> Python batch runner: origin-time load + update-time sweep + attempt manifest
      -> JSONL files in Snowflake internal stage
      -> COPY INTO RAW_EVENT_RECORDS (payload VARIANT)
      -> reconcile COPY results, then invoke Snowpark procedure
      -> Snowpark validation and revision resolution
      -> EVENT_REVISION fact + EVENT_CURRENT view + dimensions
      -> analytical marts and Snowsight queries

There is no Snowpipe Streaming, Snowflake Stream, or claim of sub-minute streaming. A batch load is the core path. Cortex and recovery drills are optional follow-on demonstrations.

MVP target: roughly 4–6 evenings if the Snowflake account and role are ready. Plan roughly 6–8 evenings total if account setup, recovery, tests, and documentation are new. These are estimates, not measured build times.

| Core MVP | After the MVP | Out of scope |
|---|---|---|
| Bounded FDSN batch extraction with overlap, window audit, and manifest | Clone isolation and Time Travel recovery drill in a sandbox | Safety guidance or alerting service |
| Internal stage + `COPY INTO` into raw VARIANT | Optional, evaluated on-demand Cortex brief | Snowpipe Streaming, Kafka, Spark, or Airflow |
| Snowpark validation, revision history, dimensions, and current view | GitHub Actions CI and repeatable SQL bootstrap | Full infrastructure-as-code platform |
| Reconciliation, rejects, coverage and latency views | Optional local metrics endpoint | Private coordinates or unmeasured production claims |

### Phased build

| Phase | Estimate | Main work | Exit evidence |
|---|---:|---|---|
| 0. Source and account check | 0.5 evening | Set public city-center coordinates for Seattle, San Francisco, and Anchorage; set 250 km radius and five-year event horizon; verify FDSN parameters, Snowflake role, stage, and Snowpark runtime; save fixtures | Example config and environment note with verified access and actual blockers |
| 1. Batch extract and raw load | 1–1.5 evenings | Origin-time history load, update-time sweep, overlap, count-sized windows, attempt manifest, internal stage, `COPY INTO`, raw VARIANT table | A repeatable batch appears in RAW with matching attempt and load counts |
| 2. Warehouse models | 1.5–2 evenings | Snowpark validation, rejects, deduplicated revisions, facts, dimensions, current view | Revision, old-event update, tombstone, and rerun fixtures produce expected results |
| 3. Quality and evidence | 1–2 evenings | SQL uniqueness/reconciliation checks, coverage and health views, CI, sample analysis | Actual run evidence and results documented separately from targets |
| 4. Optional demos | 1–2 evenings | Clone/Time Travel, Cortex evaluation, documentation polish | Each optional demo has evidence, limitations, and actual usage data |

## Source behavior and data contract

Separate the initial history load from the update sweep because event-time and update-time filters answer different questions. The initial load queries fixed five-year origin-time windows around each configured site. Each update sweep records a fixed `sweep_started_at`; it queries `updatedafter = last_committed_watermark - overlap`, with `starttime` at the configured USGS catalog lower bound and `endtime` fixed at the cutoff. Omit spatial and magnitude filters so a revised event that moves into or out of a site's radius is still observed. Use the FDSN count method to size origin-time windows, split them until each query is comfortably below the 20,000-result cap, then fetch each window in one response without offset paging. If a response reaches the cap or the before/after counts differ, split and retry; if a window cannot be split further or does not reconcile, leave it as an explicit coverage gap. Advance the committed watermark only to `sweep_started_at` after every window reconciles, then repeat the overlap on the next run. Changes made while a sweep runs are intended to be picked up by the next overlapping sweep; because the endpoint does not provide a snapshot boundary, residual gaps remain possible and must be reported. Recompute site distances in the warehouse and retain updates for events within the five-year horizon or previously relevant canonical IDs, including deletions. Record the catalog lower bound and watermark in the manifest. This is still best-effort reconciliation, not proof of a gap-free source snapshot; the API does not promise a transactionally consistent catalog snapshot. [USGS documents separate event-time and update-time filters, the 20,000-result cap, and the count method](https://earthquake.usgs.gov/fdsnws/event/1/1).

| Source behavior | Design effect |
|---|---|
| API query returns a bounded result set | Each logical request has stable parameters; every invocation/retry gets its own attempt ID, query-window counts, row counts, and status |
| Events may be revised after origin time | Keep origin, source-updated, fetched, and curated clocks separately |
| Deleted records can be returned with status | Preserve the status and model a tombstone; do not infer deletion from absence |
| Results can be late or out of order | Use source update time and deterministic tie-breakers, not event time alone |
| Preferred ID and associated IDs can change | Preserve source IDs and resolve aliases before canonical current-state reporting |
| Additive fields may appear | Keep complete source JSON in VARIANT; parser versions describe typed projections |
| Invalid row vs invalid whole response | Row-level rejects retain reason; malformed response fails the batch and preserves raw prior state |

Most USGS-produced information is public domain. Credit the U.S. Geological Survey and link to official event records. Check rights before reusing third-party graphics. Use example site coordinates in public demos; keep private coordinates out of Git.

The USGS references reviewed do not establish a fixed global API quota or uptime SLA. Treat neither as guaranteed. A transactionally consistent catalog snapshot remains unverified; do not claim complete coverage from a successful run. The warehouse is not safety guidance.

## Warehouse model and ownership

Keep only tables needed by three demonstration queries: (1) event counts and magnitude bands by year and site; (2) revision counts and source-update-to-fetch delay by site and magnitude type; (3) latest non-deleted records for the selected date window. The core fact is one distinct canonical event revision; the bridge is one event revision × configured site. Use date, site, magnitude-type, and status dimensions only where these queries use them. State each grain and enforce uniqueness in SQL; Snowflake standard-table key constraints are not enforcement by themselves. At this data volume, do not add clustering or special partitioning without query-profile evidence.

| Object | Grain / writer | Purpose |
|---|---|---|
| BATCH_ATTEMPT | One row per extract/load execution; Python runner | Stable logical batch ID, unique attempt ID, requested range, query parameters, query windows, times, load outcome, counts, and gaps |
| RAW_EVENT_RECORDS | One returned source feature per batch-attempt/query-window row; `COPY INTO` | Full payload VARIANT plus attempt ID, fetched time, file, and row metadata |
| STG_EVENT_REVISION | One validated source observation; Snowpark procedure | Typed projection, parser version, canonical/associated IDs, reject status |
| BATCH_PROCESS_ATTEMPT | One transformation invocation per loaded attempt; Snowpark procedure | Unique process-attempt ID, start/end, status, counts, and failure details; retrying processing does not refetch or rewrite the extract manifest |
| DIM_DATE | One calendar date; warehouse build | Role-playing event-date and source-update-date slicing |
| DIM_SITE | One configured public example location; warehouse build | Public coordinates and descriptive radius; no private site values |
| DIM_MAGNITUDE_TYPE | One magnitude scale/type; warehouse build | Correctly labels magnitude semantics |
| DIM_EVENT_STATUS | One source status; warehouse build | Reviewed, automatic, deleted/tombstone, and other documented values |
| FACT_EVENT_REVISION | One distinct canonical event revision; warehouse build | Event/source clocks, magnitude, coordinates, place, depth, status, source IDs, payload hash |
| BRIDGE_EVENT_SITE | One event revision × configured site; warehouse build | Epicentral distance and within-radius flag for each example location |
| FACT_BATCH_RUN | One batch attempt; warehouse build | Fetched, loaded, processed, rejected counts, latency, outcome, and gaps |
| EVENT_CURRENT | One canonical event after alias and revision rules; view | Latest non-stale, non-tombstoned state |
| Reject and health views | One rejected row or one health snapshot; views | Visible quality issues, pending work, coverage, source age, and latency |

Use source event IDs and associated IDs for canonicalization. Keep revision history in a fact table rather than overwriting the only row. Compute distance with a documented horizontal great-circle formula from longitude/latitude coordinates; it is epicentral distance, not hypocentral distance or shaking.

### Idempotent batch loading and processing

1. Create a deterministic `logical_batch_id` from the requested query window and parameters. Create a unique `attempt_id` for every extract/load invocation, including retries. Append one `BATCH_ATTEMPT` row per attempt and never overwrite a failed attempt's audit record. Give every file and row a stable source key.
2. Extract bounded origin-time windows for initial history. For updates, use `updatedafter` from the last successful update watermark minus overlap with the configured catalog-wide origin-time lower bound and no spatial/magnitude filters. Persist the attempt manifest and JSONL files before loading.
3. Upload files to an internal stage and `COPY INTO` raw records. Retain file names and load metadata for reconciliation.
4. Dedupe repeated source observations before `MERGE`. Define logical revision identity from canonical event identity, source update time, and payload hash; test duplicate unseen source keys explicitly.
5. In a transaction, merge validated revision rows and append a successful `BATCH_PROCESS_ATTEMPT` record. On failure, roll back fact changes; catch the error outside that transaction and append a failed processing-attempt record separately. Keep raw rows and extraction manifests available for retries.
6. Build dimensions and facts from durable raw/staging data. Re-running a batch converges to the same facts and counts.
7. Reconcile requested query windows to raw rows and processed/rejected results. Do not infer a complete batch merely from HTTP 200. Keep attempt outcomes separate from the logical batch's final status so a successful retry does not erase the earlier failure.

One writer per table: Python runner/COPY owns RAW_EVENT_RECORDS and BATCH_ATTEMPT; the Snowpark procedure owns staging, facts, dimensions, and BATCH_PROCESS_ATTEMPT; views own current, reject, and health outputs. Keep DDL outside processing transactions. Retry the procedure from durable raw rows and expose pending batches. Snowflake Tasks are post-MVP only; a Task does not start the local extractor or detect local files unless an explicit external trigger is added.

### Revision, alias, deletion, and schema rules

- Retain USGS origin time, source updated time, fetched time, and curated time.
- Resolve current revision by source updated time, then fetched time and stable payload hash as tie-breakers.
- Preserve preferred and associated IDs; reconcile aliases so rekeys do not create duplicate current events.
- Preserve status. A deleted record creates a tombstone; stale backfill must not resurrect it.
- Do not discard a valid record only because origin time is old.
- VARIANT retains unknown fields; parser version tracks the typed projection.
- Invalid rows become rejects with reason and count. A malformed whole response fails the batch.
- On contract change, bump parser version, replay retained raw in a sandbox, compare outputs and reject counts, then promote.

## Orchestration, observability, and recovery

The MVP is a command-driven batch pipeline with one explicit orchestrator: Python performs extraction, upload, `COPY INTO`, reconciliation, and the procedure call. Do not imply that a Snowflake Task notices local files or starts the Python extractor. A later scheduler may invoke the whole runner; Snowflake Tasks are optional for warehouse-only steps after loading. Do not add Airflow for this small single-warehouse graph.

Report separately: last successful batch age; newest source-updated age; fetch-to-curated latency; requested/loaded/processed/rejected rows; pending batches; processing-attempt status; duplicate fact keys; window count/reconciliation results; and coverage gaps.

Set a target and sample period before measuring. Use a meaningful sample count and show the distribution, sample dates, and actual query/run evidence. `fetch-to-curated` measures this local pipeline only; it excludes USGS publication delay. These are project acceptance measures, not production SLOs.

Required recovery evidence:

1. Load a batch successfully, fail a transform, and show the durable raw data and failed/pending manifest.
2. Retry processing without refetching; show unchanged logical revision counts and no duplicate fact keys.
3. Replay an overlapping batch and show convergence.
4. In a sandbox, clone only the small fact table, mutate the clone, and confirm the source is unchanged.
5. For Time Travel, suspend the sandbox writer, capture the inner `MERGE` query ID, make a deliberate bad merge, and query/clone `BEFORE` that statement. Show before/after counts and recovery from raw.

Standard Time Travel retention is one day; longer retention for permanent tables requires Enterprise or higher. Statement-ID access has a separate 14-day limit. Clones start zero-copy, but divergence/history can incur storage. Drop demo clones.

## Cortex brief

Cortex is explicit and on demand. It may turn a bounded analytical result into a short factual summary: event count in a selected window, nearest event, magnitude, record age, and source status. It must not infer risk, shaking, damage, or action. Keep the feature only if a user test shows it is easier to scan than the deterministic SQL result.

Controls: cap rows/tokens; allow one bounded retry; cache by aggregate hash; persist model/time/input hash if saving a brief; use deterministic fallback on access/error/unsafe output. Evaluate roughly 10 saved aggregates, check every fact against SQL, and reject hazard/action language. Cortex usage-history data can lag by up to five minutes; warehouse credits are separate. Do not claim cost before measuring.

## Tests, CI, privacy, and cost

**Fixture tests:** timestamps, coordinates, missing IDs, unknown fields, late arrival, repeated/overlapping batches, an old-event update outside the initial recent window, an event moving into/out of a site radius, revision winner, alias rekey, tombstone/stale replay, malformed response, row rejects, duplicate unseen merge keys, over-limit window splitting, count mismatch/retry, unresolved-window gap reporting, and watermark not advancing on failure.

**Snowflake integration checks:** `COPY INTO` repeat behavior, batch failure/retry, merge-plus-processing-log transaction, and stored-procedure package/runtime availability. Run manually or behind an explicit gate; keep account secrets out of the fixture job.

**CI:** GitHub Actions runs locked dependency install and secret-free fixture tests. Add a badge only after a real workflow run. Snowflake integration tests require an explicitly configured account and must be gated.

**Security:** keep key-pair authentication outside Git; use least privilege; ignore `.env`; use example-only `.env.example`; never commit a private site coordinate or account secret.

**Cost:** Local extraction is effectively zero. Estimate Snowflake warehouse, storage, stage, and optional Cortex use from measured query/account history. `COPY INTO` and Snowpark transformations require warehouse compute. Use XS compute, auto-suspend, short sessions, keep optional Tasks suspended while idle, and drop temporary clones. Any hours or credits in the plan are a usage scenario, not a bill forecast; account region, edition, trial balance, compute minimums, pricing, and activity vary. Cortex usage history and warehouse credit consumption are separate.

## Repository layout

The layout planned here was superseded during implementation. See the [README](../README.md#repository-layout) for the current layout.

## Demo and acceptance checklist

Two-minute demo: 0:00–0:15 problem and safe claim; 0:15–0:35 bounded request and manifest; 0:35–0:55 staged JSONL and raw VARIANT row; 0:55–1:15 Snowpark fact/dimension build and current view; 1:15–1:35 overlapping rerun and revision history; 1:35–1:50 failed transform retry or clone/Time Travel if complete; 1:50–2:00 analytical query, actual evidence, and limitations. Planned steps must not be shown as completed.

Status as of 2 October 2026. Each ticked item links to its evidence.

- [x] Choose public example sites/radii and state limitations. ([settings](../src/quakewatch/settings.py), [README](../README.md))
- [x] Save normal, revision, deletion, malformed, additive-field, over-limit, count-mismatch, and incomplete-window fixtures. ([fixtures](../tests/fixtures/README.md))
- [x] Implement initial per-site origin-time windows plus catalog-wide `updatedafter` sweep, overlap, query-window audit, and append-only attempt/process manifests. The sweep is implemented but has not completed live; see [limitations](results.md#still-open).
- [x] Create Snowflake stage, RAW_EVENT_RECORDS VARIANT table, role, and key-pair auth outside Git. ([environment check](environment.md))
- [x] Load JSONL files with `COPY INTO`; reconcile files, query windows, and counts. 177 of 180 windows loaded; 3 source gaps.
- [x] Create typed staging, reject handling, dimensions, revision fact, site bridge, batch fact, and current view. ([data dictionary](data-dictionary.md))
- [x] Implement alias/tombstone rules, revision ranking, distance, and dedupe-before-`MERGE`.
- [x] Demonstrate idempotent overlapping batch, old-event update capture, transform retry, and current-key uniqueness. Proven on isolated fixtures; old-event capture by a live sweep is still open.
- [x] Add data-quality, coverage, and health queries. ([SQL](../sql/README.md))
- [x] Measure a stated sample; publish actual results with dates and evidence. The latency target was missed and is reported. ([results](results.md))
- [ ] Ask one target user if historical comparison is useful. **Deferred:** no participant has been recruited, so usefulness for facilities analysts is unconfirmed and no usefulness claim is made. The [interview guide](target-user-interview.md) is ready.
- [x] Complete clone/Time Travel and Cortex only after core batch recovery works. ([close-out](phase4-closeout.md))
- [x] Run GitHub Actions fixture CI; link only a real status badge.

## Risks and known limits

| Risk / limit | Mitigation or honest boundary |
|---|---|
| Source changes during a sweep or a query window exceeds the cap | Split windows, compare counts, repeat the overlap, and disclose unresolved coverage gaps; do not claim a consistent source snapshot |
| Source publication delay | Show source age separately from local pipeline latency |
| Account/package/region access unavailable | Verify early; report the blocker; do not claim a working Snowflake path |
| Rekey/delete creates stale or duplicate state | Preserve aliases/status; test tombstone and stale replay |
| Transform failure after raw load | Retry from durable raw rows and manifest |
| Schema drift | Preserve VARIANT, version parser, test and replay in sandbox |
| Cortex unavailable or unsafe | Deterministic fallback; no safety language |
| Private site coordinate | Public examples only; private values stay local and ignored |
| Small sample | State dates and row/batch counts; keep target separate from result |

QuakeWatch demonstrates a focused batch-warehouse slice: extraction, SQL/data modeling, Python processing, quality, backfills, and reproducibility. It does not by itself prove broad cloud infrastructure, distributed processing, production ownership, cross-team delivery, or sustained product outcomes.

## Close-out and claim boundary

A strong close-out has a tagged release, reproducible setup, real CI run, measured load/warehouse usage, completed retry evidence, documented coverage, and a retrospective comparing estimates with actual evenings.

This project demonstrates one focused Snowflake batch warehouse; it does not alone prove production operations, broad cloud infrastructure, distributed processing, cross-team delivery, or long-term product outcomes.

## Sources

Official references for implementation planning. Recheck service behavior, versions, pricing, and account compatibility before building. USGS does not document a transactionally consistent catalog snapshot, so gap-free sweep completeness remains unverified.

- **USGS source and attribution:** [credit policy](https://www.usgs.gov/information-policies-and-instructions/acknowledging-or-crediting-usgs), [GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php), [feed FAQ](https://www.usgs.gov/faqs/how-quickly-earthquake-information-posted-usgs-website-and-sent-out-earthquake-notification), [ComCat](https://earthquake.usgs.gov/data/comcat/), and [FDSN Event API](https://earthquake.usgs.gov/fdsnws/event/1/1).
- **Snowflake batch loading and modeling:** [COPY INTO table](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table), [loading local files](https://docs.snowflake.com/en/user-guide/data-load-local-file-system-copy), [Python procedures](https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-overview), [Snowpark setup](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup), and [Tasks](https://docs.snowflake.com/en/user-guide/tasks-intro).
- **Transactions and merge:** [transactions](https://docs.snowflake.com/en/sql-reference/transactions) and [MERGE](https://docs.snowflake.com/en/sql-reference/sql/merge).
- **Recovery:** [Time Travel](https://docs.snowflake.com/en/user-guide/data-time-travel), [AT/BEFORE](https://docs.snowflake.com/en/sql-reference/constructs/at-before), and [object cloning](https://docs.snowflake.com/en/user-guide/object-clone).
- **Cortex:** [AI_COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string), [regional availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability), [usage history](https://docs.snowflake.com/en/sql-reference/account-usage/cortex_ai_functions_usage_history), and [costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost).
- **Alternatives:** [NWS API](https://www.weather.gov/documentation/services-web-api) and [OpenAQ API](https://docs.openaq.org/about/about).
