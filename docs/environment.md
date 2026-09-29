# Phase 0 environment check

Checked 2026-09-29. This records Phase 0 source and account checks; raw loading and warehouse models are still future phases.

## Verified

- The repository selects Python 3.12 in `.python-version` and `pyproject.toml`. The locked local install completed with `uv sync --locked --no-editable`.
- Public example sites are Seattle, San Francisco, and Anchorage, each with a 250 km radius in `src/quakewatch/settings.py`.
- The public settings record a five-year event-time horizon with `EVENT_HORIZON_YEARS = 5`. The extractor still requires an explicit bounded range for each run.
- A bounded USGS FDSN GeoJSON request for Seattle on 2026-09-28 UTC returned 15 features. The count before and after was 15, and 15 JSONL rows were saved locally. See [results](results.md).
- The first public source feature from that capture (USGS event `uw714110682`) is saved unchanged as a GeoJSON feature in `tests/fixtures/normal_event.json` for offline tests. A clearly labeled synthetic later revision and a separately fetched real deleted feature are also saved; see [fixture provenance](../tests/fixtures/README.md).
- The local Snowflake CLI has an admin connection, `quakewatch_admin`, and a key-pair project connection, `quakewatch_project`. A read-only SQL query succeeded using role `ACCOUNTADMIN` and warehouse `COMPUTE_WH`. The CLI credentials are stored outside this repository.
- The account's package catalog lists Python runtime 3.12 and `snowflake-snowpark-python` for that runtime, including version 1.55.0. No procedure dependency has been pinned yet.
- On 2026-09-29, `sql/phase0_bootstrap.sql` completed through the `quakewatch_admin` CLI profile. Snowflake reported creation of `QUAKEWATCH_ROLE`, database `QUAKEWATCH`, schemas `RAW` and `CURATED`, warehouse `QUAKEWATCH_WH`, and stage `QUAKEWATCH.RAW.USGS_JSON_STAGE`.
- Metadata verification showed `QUAKEWATCH_WH` as `SUSPENDED`, X-Small, with 60-second auto-suspend and auto-resume enabled. `USGS_JSON_STAGE` is an internal stage. `SHOW GRANTS TO ROLE QUAKEWATCH_ROLE` confirmed database/schema/warehouse `USAGE`, stage `READ`/`WRITE`, `CREATE TABLE` on both project schemas, and `CREATE VIEW`/`CREATE PROCEDURE` on `CURATED`.
- On 2026-09-29, an encrypted local private key and its public key were created outside Git under the user's Snowflake key directory. Snowflake registered the named `QUAKEWATCH_KEY` public key for `KARTHIK12MOHAN`. `SHOW USER KEY PAIRS` reported it `ACTIVE` with `ROLE_SCOPE = QUAKEWATCH_ROLE`. The private key and passphrase were not recorded here.
- `snow connection test -c quakewatch_project` returned `Status: OK` with role `QUAKEWATCH_ROLE`, database `QUAKEWATCH`, and warehouse `QUAKEWATCH_WH`. A subsequent `SHOW WAREHOUSES` reported `QUAKEWATCH_WH` still `SUSPENDED`.
- The Phase 0 exit audit reran five offline extractor tests successfully, parsed all seven JSON fixtures, and checked the ignored live capture: one reconciled query window (`15` before, `15` returned, `15` after), 15 saved JSONL rows, and an exact match between the first row's `source_feature` and `tests/fixtures/normal_event.json`.

## Phase 0 exit status

The design's Phase 0 exit evidence is present: public example configuration, bounded FDSN access evidence, saved fixtures, verified Snowflake role/stage/runtime, and this environment note. No known Phase 0 access blocker remains. The source capture is one audited window, not a claim of complete historical coverage.

## Work in later phases

- A connection test verifies authentication and session context. Actual stage upload, `COPY INTO`, table writes, and procedure creation remain Phase 1/2 implementation and integration checks.
- The Phase 0 fixture set now includes normal, synthetic revision, real deletion, malformed response, additive field, count mismatch, over-limit, and incomplete-window cases. Offline tests cover response parsing and several window outcomes. More scenario tests and the full Phase 1 batch path remain to be built.
- A failed unresolved window currently writes a failed manifest with the window ID and error text, but `window_audit` is empty because the extractor fills it only after a successful `fetch_window` return. Structured gap reporting remains a Phase 1 implementation task.

No passwords, private keys, or private site coordinates belong in this note or in Git.
