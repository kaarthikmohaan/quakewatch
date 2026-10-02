# Phase 2 one-attempt idempotency rerun

Prepared and executed 2026-09-30. The measured result is in [results.md](../results.md).

The first Snowpark pilot processed the existing 15-row Seattle attempt `20260929T075452Z-26375840ea` and left 15 staged rows, 15 revision facts, 45 site bridge rows, one batch fact, one complete processing audit, and three public sites. This check processes **that same load attempt once more**; it does not re-extract USGS data, upload a file, or create schema objects.

Run the offline preview with `PYTHONPATH=src:. .venv/bin/python scripts/evidence/phase2/phase2_rerun_check.py`. It does not connect. After separate owner approval for possible compute cost and curated-row deletion, add `--execute`. The connector prompts for the existing encrypted key passphrase privately in the terminal.

The live command first requires the original 15-row complete RAW receipt, exact first-pilot curated counts, the known first processing-attempt ID, and no duplicate revision or bridge keys. It then calls the existing procedure **once** and checks that `revision_rows_merged=0`, staging/fact/bridge/batch/site counts do not change, and the append-only processing log grows from one to two rows. The new log must be complete with zero merged revisions, and the batch fact must point to its new process-attempt ID. Any mismatch stops for investigation. A procedure error may itself append a failed processing-attempt row after rolling back model work.

The procedure contains conditional alias-collision deletion of curated fact/bridge duplicates. None is expected for this unchanged 15-row attempt; approval is still required before execution because the code can delete curated rows if an unexpected alias conflict appears. RAW and staged source records are not deleted. This run will use the X-Small warehouse again. At the documented Gen1 rate of 1 credit/hour with a 60-second minimum, the minimum is about 0.017 credit; 2–6 minutes including idle time would be about 0.033–0.100 credits. This is a scenario, not a cap or dollar quote; actual credits and the account's price remain unmeasured. [Snowflake warehouse billing](https://docs.snowflake.com/en/user-guide/warehouses-overview).

The approved live rerun completed with zero revision rows merged, unchanged model counts, and a second complete processing audit. See [measured results](../results.md). Do not execute this guarded command again: its preflight requires the first-pilot processing-audit count of one and will now stop.
