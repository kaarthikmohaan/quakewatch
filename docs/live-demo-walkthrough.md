# Live demo walkthrough (2 October 2026)

This page walks through one recorded end-to-end run: an existing Seattle batch,
warehouse checks, one Cortex call, an isolated recovery drill, and the local
tests. The batch had already been loaded and processed when these commands ran,
and the demo drivers contain fixed names and dates. For setup and the full set
of operating commands, see the [README](../README.md#quickstart) and the
[operations reference](operations-reference.md).

## The path in one view

```text
USGS earthquake records
  -> bounded Python fetch
  -> events.jsonl + manifest.json
  -> Snowflake file stage -> COPY INTO RAW_EVENT_RECORDS
  -> Snowpark procedure -> revisions, current events, site distances, audits
  -> SQL analysis and quality checks
  -> optional Cortex brief checked against the SQL facts

Separate optional drill: clone a five-row test table -> change the clone
  -> read its earlier value with Time Travel -> remove the clone
```

The saved batch used the public Seattle point and 28 September 2026 in
Coordinated Universal Time (UTC). It checked source rows within 250 km. This is
historical analysis, not an earthquake alert, shaking estimate, or safety
assessment.

## 1. Environment and access

Python 3.12 and `uv` were already installed. The core check used the existing
`quakewatch_project` key-pair connection under `QUAKEWATCH_ROLE` and
`QUAKEWATCH_WH`. Its key passphrase was entered at the hidden terminal prompt,
not placed in a command or repository file. The Cortex, recovery, and read-only
analysis drivers used a locally configured profile but explicitly selected and
checked the same project role and warehouse before querying.

The repository has the [bootstrap SQL](../sql/setup/01_bootstrap_admin.sql), locked
[Python dependencies](../uv.lock), and an isolated fixture database for tests.
The bootstrap defines an X-Small warehouse with 60-second auto-suspend;
warehouse use can incur credits.
This run did not create account objects or make a new USGS request.

## 2. Source batch used in this run

The existing attempt was `20261002T045249Z-ee3a351be3`. Its extractor output
was already saved as `manifest.json` and `events.jsonl` under the local,
Git-ignored `data/raw/20261002T045249Z-ee3a351be3/` folder. These files are
not in GitHub.

| Source check in the saved manifest | Value |
|---|---:|
| USGS count before fetch | 15 |
| Features returned | 15 |
| USGS count after fetch | 15 |
| JSONL (JSON Lines) records saved | 15 |
| Window result | Reconciled |

No fetch command appears in this terminal run. The full source feature is kept
with attempt ID, fetch time, window ID,
parser version, and payload hash. Matching counts support this bounded batch;
they do not prove that the full USGS catalogue has no gaps.

## 3. Preview the load and check the existing RAW rows

The local preview command was:

```bash
PYTHONPATH=src .venv/bin/python -m quakewatch.raw_load \
  data/raw/20261002T045249Z-ee3a351be3/manifest.json
```

It reported 15 expected rows, the local file path, and the stage path
`@QUAKEWATCH.RAW.USGS_JSON_STAGE/20261002T045249Z-ee3a351be3`. It said
`No upload, COPY, or account connection performed.` The
[fixed-input core driver](../scripts/evidence/live_demo_2026_10_02/core.py)
then ran from a temporary copy of that file. It printed `already_loaded` with 15 rows. It did not upload,
`COPY INTO`, or append another receipt in this run. The original loader logic
and [COPY mapping](../sql/load/copy_raw.sql) are in the repository.

RAW keeps the original source record. This attempt has its own ID even though
its request window overlaps the earlier Seattle sample.
Neither the 30 sample observations nor the warehouse total are counts of 30
new earthquakes.

## 4. Check the processed batch

The core driver checked the existing health row. Both before and after the
check it was `RECONCILED`: 15 loaded, 15 RAW, 15 staged, 15 processed, and zero
rejected rows. The driver did **not** call
`QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT` again.

| Health check | Value before and after |
|---|---:|
| Loaded, RAW, staged, processed rows | 15 each |
| Rejected rows | 0 |
| Status | `RECONCILED` |

The [Snowpark procedure](../src/quakewatch/snowpark_procedure.py) validates
fields, records rejected rows, maintains event versions, updates the latest
non-deleted view, calculates event-to-site distances, and writes batch and
processing audits when a new attempt is processed. This terminal run only
checked its already processed result.

The main warehouse objects are described in the [data dictionary](data-dictionary.md).

| Object | What it holds |
|---|---|
| `RAW_EVENT_RECORDS` | Original source features and capture metadata |
| `STG_EVENT_REVISION` | Checked and typed source observations, including rejects |
| `FACT_EVENT_REVISION` and `EVENT_CURRENT` | Version history and the latest non-deleted event |
| `BRIDGE_EVENT_SITE` and dimensions | Distance and links to public example sites |
| `FACT_BATCH_RUN` and process attempts | Row counts, timings, status, and retry history |

## 5. Query and check the warehouse

The [fixed-input live checks](../scripts/evidence/live_demo_2026_10_02/checks.py)
ran from a temporary copy of that file. They used the reviewed
[Seattle analysis](../sql/analysis/sample_seattle_day.sql),
[reconciliation checks](../sql/checks/reconciliation.sql), and
[duplicate-key checks](../sql/checks/uniqueness.sql). The Seattle result was
**15 current events** within the configured radius, with magnitudes from
**0.66 to 2.56**. Their earliest and latest origin times were
`2026-09-28 00:05:15.410 UTC` and `2026-09-28 22:32:25.040 UTC`.

| Warehouse-wide live check | Result |
|---|---:|
| Reconciled batch receipts | 179 |
| Loaded, RAW, staged, processed observations | 216,391 each |
| Rejected observations | 485 |
| Batch or loaded-window anomalies | 0 |
| Duplicate revision or site-link key groups | 0 |

The total includes 177 historical attempts and two overlapping 15-row Seattle
samples. The 485 older rejects were grouped as `invalid_origin_time` in the
previous post-run check. The live quality run checked their total, but did not
repeat the reason grouping.

The same live read-only run queried ten fixed public-site cases from
[reviewed aggregate SQL](../sql/analysis/site_year_aggregates.sql). The counts of
currently modelled events matched the earlier saved snapshot:

| Public site | 2022 | 2024 | 2026 through 29 September UTC |
|---|---:|---:|---:|
| Anchorage | 22,056 | 21,711 | 10,685 |
| Seattle | 2,651 | 3,514 | 2,469 |
| San Francisco | 15,975 | 18,859 | 16,183 |

The tenth case was the Seattle day, with 15 modelled events. These are counts
from the loaded warehouse rows, not proof of complete source coverage.

## 6. Changes, deletions, reruns, and failure recovery

These behaviours were tested in an isolated Snowflake fixture database. They were **not repeated** on the new live Seattle batch:

| Case | Verified behaviour |
|---|---|
| Later source correction | Keep both versions; show the later one as current |
| Old event updated later | Keep the old origin date and the new source version |
| Source deletion | Keep a tombstone in history; hide the event from `EVENT_CURRENT` |
| Stale replay or overlapping batch | Do not add duplicate logical version or restore a deleted event |
| Failed transformation | Keep RAW and a failed audit; retry processing without another source fetch |

The [Phase 2 results](evidence/results-log.md#phase-2-exit-review-2026-10-01) and
[recovery results](evidence/results-log.md#isolated-failed-transform-and-retry-drill) give
the fixture counts and limits. The warehouse checks in this terminal run found
zero revision and site-link duplicate groups.

## 7. Historical coverage and update sweep

The historical backfill previously loaded and processed **177 of 180** planned
windows, with **216,361** RAW observations. Windows **12, 42, and 73** remain
USGS source gaps. The batch checked here covers an already represented Seattle
day; this terminal run did not fetch or fill those windows.

The catalog-wide `updatedafter` sweep is designed to find changed or deleted
older records. Earlier live attempts stopped at a source timeout, and no
complete sweep was loaded or committed. No update watermark had been committed
at the time of this demo, so none advanced. See the
[operations reference](operations-reference.md#update-sweep-preview) for its
planning, extraction, and guarded load steps.

## 8. Cortex brief

The [Cortex trial](../scripts/evidence/phase4/cortex_trial.py) ran with
`PYTHONPATH=src:. .venv/bin/python scripts/evidence/phase4/cortex_trial.py --execute`.
It made one
`AI_COMPLETE` call with `llama3.1-8b` and a 120-token output cap. Only SQL
aggregate facts went into the prompt, not raw records, coordinates, or
credentials. The SQL facts said 15 modelled Seattle-day events; nearest event
`uw714111042` was **42.1 km from the site**, magnitude **1.23**, status
`reviewed`, and **78.6 hours old** at query time.

**The brief was rejected.** The generated sentence described the distance as
measured from the event ID rather than from the site. Local fact validation
caught the error, so the SQL facts above were shown instead. The same error had
caused an earlier rejection that day.

Query ID: `01c77438-0002-b28e-000e-fef20003c0ca`; the call
used 141 prompt and 76 completion tokens, and its credits have not been
measured. The supporting count and nearest query IDs were
`01c77438-0002-b28e-000e-fef20003c0c6` and
`01c77438-0002-b3cf-000e-fef20004108a`.

## 9. Clone and Time Travel recovery

The [fixed-input recovery driver](../scripts/evidence/live_demo_2026_10_02/recovery.py)
ran from a temporary copy of that file. It used only the isolated five-row fixture table. It created a uniquely named
clone, changed one clone magnitude from **1.1 to 1001.1**, and checked that
the source table still held **1.1**. Snowflake Time Travel returned the clone's
original **1.1** from before the change.

The driver then removed only that verified demo clone and checked it was gone.
The main QuakeWatch fact table was not changed. Clone, change, and removal
query IDs were `01c77439-0002-b28e-000e-fef20003c0d6`,
`01c77439-0002-b2f7-000e-fef2000400aa`, and
`01c77439-0002-b2f7-000e-fef2000400b2`.

## 10. Tests, automation, privacy, and cost

Local test discovery ran with:

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
```

All **303** tests passed. The [GitHub Actions workflow](../.github/workflows/ci.yml)
installs locked dependencies, builds synthetic fixtures, and runs the same
secret-free tests on every push.
The 50-window preview and two small RAW-load messages printed during the test
run came from test cases, not new USGS requests or Snowflake loads.

Public site coordinates are used. Source files and account keys stay
out of Git; the private key passphrase belongs only in the terminal prompt.
Cortex receives checked aggregate facts, and its output is rejected when it
misstates them.

## What to run next time

| Command or step | Reuse for a new batch? |
|---|---|
| `quakewatch-extract` with a new site and UTC range | Yes; it creates a new attempt ID |
| `quakewatch.raw_load` preview with that attempt's manifest | Yes; local check only |
| Fixed-input core driver | Yes, for an already loaded batch: pass its manifest path as the first argument (defaults to the recorded 2 October batch) |
| Fixed-input recovery driver | Only the named test clone; it creates and removes paid objects |
| Cortex trial | Only for a separately chosen paid, bounded case |
| Live checks driver | Read-only but its analysis dates are fixed |
| Local `unittest` command | Yes |

Any new Snowflake or Cortex run can incur credits; check
the current account state. This demo did not rerun the five-year backfill, complete the update sweep, measure a
new credit bill, or conduct the target-analyst interview.

For exact counts and query IDs, see the
[2 October evidence entry](evidence/results-log.md#live-end-to-end-seattle-demo-2026-10-02). For the model and
source limits, see [design](design.md) and the [data dictionary](data-dictionary.md).
