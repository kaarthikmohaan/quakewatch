# Phase 4 optional Cortex evaluation

This page records the optional Cortex brief evaluation, run on 1 October 2026
after the original Phase 4 close-out. A brief turns one saved SQL aggregate
into a short factual sentence. The SQL result is always the fallback, and a
brief is shown only if every fact in it matches the SQL row.

## Outcome

| Measure | Result |
|---|---|
| Briefs that passed local validation and human fact review | **9 of 9** in the evaluation |
| Briefs rejected | **4**: two Seattle-day trials before the evaluation ([trial](results-log.md#phase-4-cortex-trial-attempt)) and two in the [2 October demo](results-log.md#live-end-to-end-seattle-demo-2026-10-02); each was replaced by the SQL facts |
| Measured AI credits | **0.003948756** for the first 11 completed calls; the two 2 October calls are unmeasured |
| Usefulness | One comparison by the project author preferred the brief for scanning. This is not user evidence; the [target-analyst interview](../target-user-interview.md) is still required |

## Ten saved aggregate cases

The [reviewed SQL](../../sql/analysis/site_year_aggregates.sql) defines three public
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

The [runner](../../scripts/evidence/phase4/cortex_aggregates.py) previews by
default. With `--execute`, it runs the single SQL query as `QUAKEWATCH_ROLE` on
`QUAKEWATCH_WH`, validates the ten case IDs and 250 km radii, and saves
`data/cortex/phase4_aggregates.json`, which Git ignores. The file records the
SQL query ID, SQL hash, per-case input hashes, and snapshot time. No Cortex call
occurs in this step.

The query ran on 2026-10-01 and saved all ten cases, each with a nonzero count
and valid nearest-event fields. The query ID and counts are in the
[evidence log](results-log.md#phase-4-ten-case-cortex-aggregate-snapshot).
Record ages describe the snapshot time, not later use.

## Evaluation design

The [evaluator](../../scripts/evidence/phase4/cortex_evaluate.py) used
`claude-haiku-4-5`, which a model-listing command showed as available to
`QUAKEWATCH_ROLE`; a read-only grant listing confirmed `USE AI FUNCTIONS` and
`SNOWFLAKE.CORTEX_USER` through `PUBLIC`. It excluded the Seattle day, which
had already used its one allowed retry in the earlier trial, so the nine
remaining cases got at most nine `AI_COMPLETE` calls. Prompts were limited to
1,200 characters and output to 120 tokens.

Safeguards:

- **No duplicate paid calls.** A pre-call cache marker stops a lost response
  from triggering a second call on rerun. Results are cached by aggregate input
  hash in Git-ignored `data/cortex/phase4_briefs.json`, with model, time,
  prompt and input hashes, query ID, token usage, output, and validation result.
- **No automatic retry.** `--retry-case <case-id>` allows one deliberate retry
  of a completed rejected or failed case and keeps the first attempt. An
  interrupted attempt needs manual investigation before any retry.
- **Strict local validation.** A brief must state the supplied count, 250 km
  radius, nearest event ID, distance **from the site**, magnitude, status,
  record age, and modeled-sample wording. Hazard or action language,
  complete-coverage claims, and truncated output are rejected.
- **Human review.** Even a passing brief is compared claim by claim with its
  SQL row before it counts as correct.

## Results

The nine-call batch ran on 2026-10-01. All nine briefs passed local validation
and human review against every SQL fact, and the cache records each verdict. A
rerun made zero new calls because every input hash was cached. Token totals
are in the [evidence log](results-log.md#phase-4-nine-case-cortex-evaluation).

In one side-by-side comparison (Seattle 2024), the project author found the
brief easier to scan than the SQL row. That is enough to keep the brief as an
optional feature with SQL fallback, but not to claim it helps users.

## Cost

The [metering runner](../../scripts/evidence/phase4/cortex_metering.py)
collected the eleven completed query IDs (two Seattle trials and nine annual
cases) and read `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` once as `ACCOUNTADMIN`. It
did not call Cortex or change billing. All eleven calls appeared, totaling
**0.003948756 AI credits**; the per-model split is in the
[evidence log](results-log.md#phase-4-nine-case-cortex-evaluation).
This excludes warehouse compute, which is measured separately as shared
warehouse hours, and is not a per-demo bill.

The four Cortex test files run offline as part of the standard `unittest`
suite.
