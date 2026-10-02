# Two-minute QuakeWatch demo

Use the recorded evidence below. Do not rerun live source or Snowflake work
for a presentation without a new cost and data-state check.

| Time | Present |
|---|---|
| 0:00–0:15 | **Problem.** Compare historical USGS earthquake records near three public example cities. QuakeWatch is retrospective batch analysis, not an alert or risk estimate. |
| 0:15–0:35 | **Source contract.** A bounded FDSN request writes full GeoJSON features and a manifest with query-window counts. The first Seattle UTC-day example reconciled 15 before/fetched/after rows. |
| 0:35–0:55 | **RAW.** JSONL goes to the Snowflake internal stage and `COPY INTO` a VARIANT raw table. The loader reconciled 177 history attempts and 216,361 RAW rows; three requested history windows remain missing. |
| 0:55–1:15 | **Model.** A Snowpark procedure inside Snowflake projects typed staging, keeps rejects, and builds revision facts, site bridges, dimensions, and a current view. All 177 loaded history attempts were processed; 485 rows were rejected with an audited reason. |
| 1:15–1:35 | **Revisions and reruns.** An unchanged Seattle rerun added no logical revisions. Isolated fixtures showed an old-event update, a tombstone, an overlapping replay, and retry from durable RAW after a first transform failure. |
| 1:35–1:50 | **Recovery.** A five-row fixture fact was cloned; a bad `MERGE` changed only the clone. `BEFORE` the MERGE returned the earlier value. The demo clone was subsequently dropped. |
| 1:50–2:00 | **Evidence and limits.** A dated Seattle sample returned 15 current events. The first-backfill p95 was 35.9 hours against a 24-hour target. The catalog-wide update sweep remains incomplete, so no complete-coverage or current-catalog claim is made. |

Evidence and query IDs: [results](results.md). Architecture and frozen
boundaries: [design](design.md).
