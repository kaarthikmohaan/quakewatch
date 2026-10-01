# Phase 4 optional Cortex evaluation

The owner reopened the optional Cortex item after accepting the original
Phase 4 close-out. Two `llama3.1-8b` briefs for the same Seattle aggregate
failed human fact review; [results.md](results.md) records the SQL facts,
query IDs, token counts, and errors. The deterministic SQL result remains the
fallback. No Cortex usefulness claim has been made.

## Ten saved aggregate cases

The [reviewed SQL](../sql/phase4_cortex_aggregates.sql) defines three public
sites (Seattle, San Francisco, Anchorage) in fixed 2022, 2024, and 2026 UTC
windows, plus one Seattle day. It returns exactly ten rows. Each row contains
the selected window, configured public radius, count of currently modeled
events within that radius, nearest event ID and distance **from the site**,
magnitude, source status, record age at query time, and check time. A zero
count has no nearest event. Rows come from `EVENT_CURRENT` joined to the
matching site bridge revision; duplicate logical event IDs are removed before
counting. The query does not include site coordinates or raw source payloads.

This is a snapshot of modeled rows, **not** proof of complete USGS coverage.
The three unresolved history windows and unfinished catalog-wide update sweep
remain disclosed. Cases with missing nearest magnitude or no events use the
deterministic fallback rather than inventing facts.

The [runner](../scripts/phase4_cortex_aggregates.py) previews by default.
After separate warehouse-cost approval, `--execute` runs the single SQL query
as `QUAKEWATCH_ROLE` on `QUAKEWATCH_WH`, validates the ten case IDs and public
250 km radii, then saves `data/cortex/phase4_aggregates.json` locally. That
path is ignored by Git. The file records the SQL query ID, SQL hash, per-case
input hashes, and snapshot timestamp. No Cortex call occurs in this step.

The owner ran this query on 2026-10-01. It saved all ten cases, each with a
nonzero count and valid nearest-event fields. The query ID and count table are
in [results.md](results.md). The saved file is a point-in-time snapshot; the
record ages describe its check time and are not live ages at later use.

## Next evaluation, after separate approval

The [offline-previewed evaluator](../scripts/phase4_cortex_evaluate.py) uses
`claude-haiku-4-5`, which a free model-listing command showed as accessible to
`QUAKEWATCH_ROLE`. A separate read-only grant listing showed `USE AI FUNCTIONS`
and `SNOWFLAKE.CORTEX_USER` granted through `PUBLIC` in this account. This
preflight does not guarantee a model call will succeed. The evaluator excludes
the Seattle day because that aggregate already
used its one allowed retry. The remaining nine saved aggregates would get at
most nine new `AI_COMPLETE` calls, with prompts no longer than 1,200 characters
and output capped at 120 tokens each. It uses the project role and warehouse,
and it makes no calls without `--execute`. A pre-call cache marker prevents a
lost response from silently causing a duplicate paid call on rerun. Results
are stored by aggregate input hash in Git-ignored `data/cortex/phase4_briefs.json`
with model, time, prompt/input hashes, query ID, token usage, output, and local
validation result. There is no automatic retry.
For a completed rejected/error case, `--retry-case <case-id>` permits one
separately approved call while retaining the first attempt; an interrupted
attempt marker is not retryable without manual investigation.

The local screen requires the supplied count, 250 km radius, nearest event ID,
distance **from the site**, magnitude, status, record age, and modeled-sample
wording. It rejects hazard/action language, complete-coverage claims, and
truncated output. Any error or rejected brief falls back to the saved SQL row.
Even a passing brief requires human comparison of every claim with that row.
Compare a factually correct brief with the SQL row in a small user scan test
before claiming it is useful. Measure Cortex AI credits and warehouse platform
credits separately from Account Usage after the usage views have populated.

The owner ran the nine-call batch on 2026-10-01. All nine saved responses
passed the local screen and subsequent human review against every saved SQL
fact. The evaluation cache records the human verdict. A rerun made zero new
calls because the input hashes were cached. [Results](results.md) records the
token totals and the estimated token-rate AI credits, while keeping actual
billed credits open. In one chat comparison (Seattle 2024), the owner chose
the Cortex brief as easier to scan than the SQL fact row. This supports
keeping the optional brief, subject to SQL fallback and the wider target-user
task interview still required by the design.

The [metering preview](../scripts/phase4_cortex_metering.py) collects the
eleven successful Cortex query IDs (two Seattle trials and nine annual cases)
from documented IDs and the local cache. After separate warehouse-cost
approval, it will read `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` once as
`ACCOUNTADMIN` and report per-query AI credits and any missing lagged rows.
It will not invoke Cortex or change account billing. Warehouse platform
credits remain a separate shared-hour measure.

The owner ran the query on 2026-10-01. All eleven completed Cortex calls
appeared, totaling **0.003948756 measured AI credits**. The metering query ID
and split by model are in [results.md](results.md). This does not include
warehouse platform credits or establish a per-demo dollar bill.

The four Cortex test files use the repository's built-in `unittest` style.
On 2026-10-01, the focused offline discovery command ran nine tests and
reported `OK`. The first attempt to run them with `pytest` found no installed
`pytest` module; no dependency was added, and the tests were converted to
the existing project style before the successful run.
