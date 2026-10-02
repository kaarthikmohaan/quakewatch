# Architecture decision records

Each record states one decision, why it was made, and its consequences. The
decisions date from the [design](../design.md) of 29 September 2026 or from
later fixes; they were written up as records on 2 October 2026.

| ADR | Decision |
|---|---|
| [0001](0001-batch-not-streaming.md) | Batch extraction instead of streaming |
| [0002](0002-revision-identity.md) | Revision identity and append-only history |
| [0003](0003-tombstones.md) | Deletions are kept as tombstones |
| [0004](0004-watermark-after-reconciliation.md) | Update watermark advances only after reconciliation |
| [0005](0005-one-writer-one-transaction.md) | One writer per table and one transaction per batch |
| [0006](0006-command-driven-orchestration.md) | Command-driven orchestration without Airflow |
| [0007](0007-no-clustering.md) | No clustering or special partitioning at this volume |
| [0008](0008-stub-records.md) | Reject USGS stub records with their own reason |
| [0009](0009-local-secret-config.md) | Credentials live in per-user Snowflake config, not .env |
| [0010](0010-live-integration-check.md) | Live integration check compiles SQL instead of running the procedure |
