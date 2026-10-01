# Phase 4 close-out snapshot

**Date:** 1 October 2026. This page compares the optional Phase 4 plan with
observed evidence. It does not declare the whole QuakeWatch design complete.

| Phase 4 item | Observed result | Limit |
|---|---|---|
| Clone isolation | Five-row fixture fact cloned; one clone-only revision magnitude changed from 1.1 to 1001.1; source stayed at 1.1 and five rows | Isolated synthetic fixture, not main warehouse recovery |
| Time Travel | `BEFORE` the captured `MERGE` query ID returned the original value and five rows | One-day table retention; statement-ID evidence ages out |
| Demo cleanup | Guarded `DROP` removed the demo clone; source remained five rows | Fixture database and test-only failure procedure remain |
| Cortex brief | Not run | Optional feature; no user comparison or token/credit measurement, so no usefulness or cost claim |
| Documentation | README, runbook, recovery plan, dated results, and two-minute demo updated | Current local commits are ahead of the last pushed CI run |
| Actual account usage | Read-only Account Usage snapshot returned 0.088875 compute credits for 08:00–09:00 UTC and 0.0705 for the still-running 09:00–10:00 hour | Shared warehouse, lagged data; no per-demo or dollar cost and no storage measurement |

The full [query IDs, counts, and limitations](results.md) remain the evidence
source. The optional recovery demo met its isolation and Time Travel checks.
Phase 4 now has actual warehouse-hour usage data, but not an isolated demo
bill or storage charge; do not convert the earlier XS estimate into measured
per-demo credits. Cortex was deliberately left out of the close-out because
it is optional and has not passed its factuality and user-value evaluation.

The owner-approved [read-only metering runner](../scripts/phase4_usage.py)
queried hourly Account Usage for `QUAKEWATCH_WH` from 08:00 to 12:00 UTC on
1 October. It returned the two rows above at 09:56 UTC; later hours were not
yet present. Snowflake says this view can lag by up to three hours. An absent
recent hour is unknown, not zero, and a shared warehouse hour cannot be
assigned wholly to the demo. The [results](results.md) include the query ID
and the cloud-services/reported-credit columns.

## Remaining core work

- Resolve or keep clearly disclosed USGS history windows 12, 42, and 73.
- Complete the catalog-wide update sweep before advancing its watermark; the
  current source timeout leaves it incomplete.
- Ask one target analyst to compare the historical query with their manual
  baseline and record usefulness and actual task time.
- Recheck final, fully posted warehouse-hour credits if a more precise cost
  comparison is needed; measure storage if accessible. Compare actual effort
  and usage with the original plan before any release claim.

The planning baseline estimated roughly 6–8 evenings including setup,
recovery, tests, and documentation. Visible implementation and live evidence
span 29 September through 1 October 2026 (three calendar days); actual hours
or evenings were not tracked, so no time-saved claim is made.

The [design](design.md) remains the project plan. The first-backfill p95 was
35.9 hours against a predeclared 24-hour target. This miss remains visible in
[results](results.md), along with the 485 typed rejects and the fact that
216,376 total observations include an overlapping 15-row Seattle pilot.
