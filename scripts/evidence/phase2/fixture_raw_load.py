"""Preview or load four synthetic RAW attempts into the isolated fixture DB."""

from __future__ import annotations

import argparse
import hashlib
import json

from quakewatch.raw_load import (
    RECEIPT_SQL,
    _result_dicts,
    connect_project,
    reconcile_loaded_rows,
    validate_local_batch,
)
from scripts.fixtures.build_phase2_fixture_attempts import SEQUENCE
from scripts.fixtures.build_phase2_fixture_bundle import DEFAULT_OUTPUT
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE
from scripts.pipeline.build_procedure_bundle import REPO_ROOT

ROOT = DEFAULT_OUTPUT / "attempts"
STAGE = f"@{TEST_DATABASE}.RAW.USGS_JSON_STAGE"
RAW_TABLE = f"{TEST_DATABASE}.RAW.RAW_EVENT_RECORDS"
RECEIPT_TABLE = f"{TEST_DATABASE}.RAW.BATCH_ATTEMPT"
COPY_TEMPLATE = (REPO_ROOT / "sql" / "load/copy_raw.sql").read_text(encoding="utf-8")


def _hash_feature(feature: dict) -> str:
    return hashlib.sha256(json.dumps(
        feature, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def local_plans(sequence: tuple[tuple[str, str], ...] = SEQUENCE) -> list[dict]:
    """Require exactly the reviewed fixture files and source identities."""
    plans = []
    for attempt_id, fixture_name in sequence:
        directory = ROOT / attempt_id
        manifest, count = validate_local_batch(directory / "manifest.json")
        if (manifest.get("attempt_id") != attempt_id or count != 1
                or manifest.get("fixture_only") is not True
                or manifest.get("fixture_source") != fixture_name
                or manifest.get("batch_kind") != "synthetic_fixture"
                or manifest.get("query_parameters", {}).get("source") != "local_synthetic_fixture"):
            raise ValueError(f"unreviewed fixture attempt: {attempt_id}")
        record = json.loads((directory / "events.jsonl").read_text(encoding="utf-8"))
        source = json.loads((REPO_ROOT / "tests" / "fixtures" / fixture_name).read_text())
        if (record["source_feature"] != source
                or record["metadata"].get("payload_hash") != _hash_feature(source)
                or record["metadata"].get("fixture_only") is not True):
            raise ValueError(f"fixture source/hash differs: {attempt_id}")
        stage_path = f"{STAGE}/{attempt_id}"
        copy_sql = COPY_TEMPLATE.replace("QUAKEWATCH.RAW.", f"{TEST_DATABASE}.RAW.")
        if "QUAKEWATCH.RAW." in copy_sql or copy_sql.count("{{ attempt_id }}") != 1:
            raise ValueError("COPY template changed; review fixture mapping")
        copy_sql = copy_sql.replace("{{ attempt_id }}", attempt_id)
        plans.append({"attempt_id": attempt_id, "manifest": manifest,
                      "events_path": directory / "events.jsonl", "stage_path": stage_path,
                      "copy_sql": copy_sql})
    return plans


def _append_receipt(cursor, plan: dict, status: str, loaded: int,
                    copy_results: list[dict], error: Exception | None = None) -> None:
    manifest = plan["manifest"]
    sql = RECEIPT_SQL.replace("QUAKEWATCH.RAW.", f"{TEST_DATABASE}.RAW.")
    if "QUAKEWATCH.RAW." in sql or f"INSERT INTO {RECEIPT_TABLE}" not in sql:
        raise ValueError("receipt SQL was not isolated")
    values = (
        manifest["attempt_id"], manifest["logical_batch_id"], manifest["batch_kind"],
        "seattle", manifest["requested_starttime"], manifest["requested_endtime"],
        json.dumps(manifest["query_parameters"]), json.dumps(manifest["window_audit"]),
        json.dumps(manifest["coverage_gaps"]), manifest["fetched_at"],
        manifest["status"], status, 1, 1, loaded,
        json.dumps([plan["stage_path"] + "/events.jsonl"]), json.dumps(copy_results),
        type(error).__name__ if error else None, str(error) if error else None,
        json.dumps(manifest),
    )
    cursor.execute(sql, values)


def _guard_empty(cursor, plans: list[dict]) -> None:
    for table in (RAW_TABLE, RECEIPT_TABLE):
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        if cursor.fetchone()[0] != 0:
            raise RuntimeError(f"fixture RAW table is not empty: {table}")
    for plan in plans:
        cursor.execute(f"LIST {plan['stage_path']}")
        if cursor.fetchall():
            raise RuntimeError(f"fixture stage path already contains files: {plan['attempt_id']}")


def execute_load() -> list[dict]:
    """Load the four reviewed test attempts once after cost approval."""
    plans = local_plans()
    results = []
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("USE WAREHOUSE QUAKEWATCH_WH")
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 300")
            _guard_empty(cursor, plans)
            for plan in plans:
                loaded = 0
                copy_results = []
                try:
                    cursor.execute(f"PUT '{plan['events_path'].as_uri()}' {plan['stage_path']} "
                                   "AUTO_COMPRESS=FALSE OVERWRITE=FALSE")
                    put = _result_dicts(cursor)
                    if len(put) != 1 or put[0].get("status", "").upper() != "UPLOADED":
                        raise RuntimeError("fixture PUT did not upload one new file")
                    cursor.execute(plan["copy_sql"])
                    copy_results = _result_dicts(cursor)
                    if len(copy_results) != 1 or copy_results[0].get("status", "").upper() != "LOADED":
                        raise RuntimeError("fixture COPY did not load one file")
                    loaded = int(copy_results[0]["rows_loaded"])
                    cursor.execute(f"SELECT COUNT(*) FROM {RAW_TABLE} WHERE ATTEMPT_ID = %s",
                                   (plan["attempt_id"],))
                    reconcile_loaded_rows(1, loaded, int(cursor.fetchone()[0]))
                except Exception as exc:
                    _append_receipt(cursor, plan, "failed", loaded, copy_results, exc)
                    raise
                _append_receipt(cursor, plan, "complete", loaded, copy_results)
                results.append({"attempt_id": plan["attempt_id"], "loaded_rows": loaded})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="load reviewed fixtures into Snowflake")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute_load(), indent=2))
    else:
        plans = local_plans()
        print("Phase 2 fixture RAW load: preview only; no Snowflake connection")
        print(f"Target: {TEST_DATABASE}; attempts: {len(plans)}; expected rows: {len(plans)}")
        print("Live order: empty RAW/stage guard, then PUT/COPY/reconcile/receipt per attempt")


if __name__ == "__main__":
    main()
