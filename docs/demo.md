# Two-minute QuakeWatch demo

Figures below are from the 2 October 2026 verification run unless marked as a
recorded drill. Do not rerun live source or Snowflake work for a presentation
without a new cost and data-state check.

| Time | Present |
|---|---|
| 0:00–0:15 | **Problem.** Compare historical USGS earthquake records near three public example cities. QuakeWatch is retrospective batch analysis, not an alert or risk estimate. |
| 0:15–0:35 | **Source contract.** A bounded FDSN request writes full GeoJSON features and a manifest with query-window counts. A fresh Seattle UTC-day capture on 2 October reconciled 15 before/fetched/after rows, 3 minutes 15 seconds after a clean clone. |
| 0:35–0:55 | **RAW.** JSONL goes to the Snowflake internal stage and `COPY INTO` a VARIANT raw table. 179 batch receipts reconcile, with 216,391 rows at every layer; three requested history windows remain missing. |
| 0:55–1:15 | **Model.** A Snowpark procedure inside Snowflake projects typed staging, keeps rejects, and builds revision facts, site bridges, dimensions, and a current view. All 179 batches are processed; 485 rows are rejected, all USGS placeholder records, with zero duplicate keys. |
| 1:15–1:35 | **Revisions and reruns** (recorded drills). An unchanged Seattle rerun added no logical revisions. Isolated fixtures showed an old-event update, a tombstone, an overlapping replay, and retry from durable RAW after a first transform failure. |
| 1:35–1:50 | **Recovery** (recorded drill). A five-row fixture fact was cloned; a bad `MERGE` changed only the clone. `BEFORE` the MERGE returned the earlier value. The demo clone was subsequently dropped. |
| 1:50–2:00 | **Evidence and limits.** The Seattle-day sample returns 15 current events. Across 179 attempts the fetch-to-curated p95 is 35.9 hours against a 24-hour target; the one batch processed as it landed took 293 seconds. All 35 SQL statements compile against the live schema. The catalog-wide update sweep remains incomplete, so no complete-coverage or current-catalog claim is made. |

Evidence and query IDs: [results](results.md) and the [verification record](evidence/results-log.md#verification-audit-2026-10-02). Architecture and frozen
boundaries: [design](design.md).
