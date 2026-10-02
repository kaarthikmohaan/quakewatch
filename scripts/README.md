# Scripts

The core pipeline lives in the `quakewatch` package under [`src/`](../src/quakewatch).
The scripts here build artifacts, run checks, or reproduce recorded evidence.
Most connect to Snowflake only with `--execute`; without it they print a plan
and change nothing. Live runs use warehouse credits, so check the
[operations reference](../docs/operations-reference.md) first.

Run everything from the repository root:

```sh
PYTHONPATH=src:. .venv/bin/python scripts/<folder>/<script>.py
```

The repository [`Makefile`](../Makefile) wraps the common steps: run
`make help` to list them. Targets marked `[EXECUTE=1]` only preview
unless you add `EXECUTE=1`; `make extract` fetches the bounded window you ask
for straight away.

## Pipeline order

| Step | Command or script | What it does |
|---|---|---|
| 0. Bootstrap | [`pipeline/bootstrap.py`](pipeline/bootstrap.py) (`make bootstrap`) | Creates the project tables and procedure after the admin setup SQL |
| 1. Plan history | `python -m quakewatch.history_plan` | Prints the bounded five-year origin-time windows |
| 2. Extract | `quakewatch-extract` or `python -m quakewatch.history_plan --resume --execute` | Fetches USGS windows into `events.jsonl` and `manifest.json` |
| 3. Load RAW | `python -m quakewatch.history_raw_load --execute` | Stages files, runs `COPY INTO`, and reconciles counts |
| 4. Build procedure | [`pipeline/build_procedure_bundle.py`](pipeline/build_procedure_bundle.py) | Builds the Snowpark procedure ZIP for upload |
| 5. Process | [`pipeline/process_history.py`](pipeline/process_history.py) (`make process`) | Calls the procedure for loaded attempts, with per-attempt checks |
| 6. Check | Scripts in [`checks/`](checks) | Reconciliation, uniqueness, health views, latency, and usage |
| 7. Update sweep | `python -m quakewatch.update_extract`, then `python -m quakewatch.update_load` | Captures later source revisions and deletions (incomplete; see [results](../docs/results.md)) |

## Folders

| Folder | Contents |
|---|---|
| [`pipeline/`](pipeline) | Steps of the regular batch path |
| [`checks/`](checks) | Read-only quality, latency, and usage checks |
| [`migrations/`](migrations) | One-off data migrations, such as the [parser version 2 release](migrations/parser_v2.py) |
| [`fixtures/`](fixtures) | Builders for the synthetic test data that CI generates before running tests |
| [`evidence/phase2/`](evidence/phase2) | One-off Phase 2 drills: pilot, rerun, revision, tombstone, old-event, and retry fixtures |
| [`evidence/phase4/`](evidence/phase4) | Optional Phase 4 drills: clone and Time Travel recovery, Cortex evaluation, and metering |
| [`evidence/live_demo_2026_10_02/`](evidence/live_demo_2026_10_02) | The fixed-input drivers used for the 2 October live demo |

Evidence scripts are kept so each recorded result can be traced to the code
that produced it. Several are one-shot by design and refuse to run twice; read
the linked plan or results entry before rerunning any of them.
