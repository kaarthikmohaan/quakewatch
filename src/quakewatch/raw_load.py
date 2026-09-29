"""Local safeguards before and after a Snowflake RAW copy."""

import json
import re
import argparse
import getpass
import tomllib
from contextlib import closing
from pathlib import Path
from typing import Any


class LoadReconciliationError(ValueError):
    """A batch cannot be marked loaded because its counts or source disagree."""


def project_connection_params(config_path: Path, passphrase: str) -> dict[str, str]:
    """Read only the dedicated key-pair profile; never use an admin profile."""
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    profile = config["connections"]["quakewatch_project"]
    if profile.get("role") != "QUAKEWATCH_ROLE":
        raise LoadReconciliationError("project profile must use QUAKEWATCH_ROLE")
    if profile.get("authenticator", "").upper() != "SNOWFLAKE_JWT":
        raise LoadReconciliationError("project profile must use key-pair authentication")
    if not passphrase:
        raise LoadReconciliationError("encrypted key passphrase is required")
    fields = ("account", "user", "private_key_file")
    if any(not profile.get(field) for field in fields):
        raise LoadReconciliationError("project profile is missing account, user, or key file")
    return {
        "account": profile["account"],
        "user": profile["user"],
        "role": "QUAKEWATCH_ROLE",
        "authenticator": "SNOWFLAKE_JWT",
        "private_key_file": profile["private_key_file"],
        "private_key_file_pwd": passphrase,
        "warehouse": "QUAKEWATCH_WH",
        "database": "QUAKEWATCH",
        "schema": "RAW",
    }


def connect_project():
    """Connect on an explicitly approved live run; prompt locally for the key."""
    import snowflake.connector

    config_path = Path.home() / ".snowflake" / "config.toml"
    passphrase = getpass.getpass("QuakeWatch key passphrase: ")
    return snowflake.connector.connect(**project_connection_params(config_path, passphrase))


def validate_local_batch(manifest_path: Path) -> tuple[dict[str, Any], int]:
    """Check a completed attempt and its JSONL file before staging it."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or manifest.get("coverage_gaps"):
        raise LoadReconciliationError("attempt is incomplete or has coverage gaps")

    events_name = manifest.get("events_file")
    if events_name != "events.jsonl":
        raise LoadReconciliationError("unexpected events file name")
    events_path = manifest_path.parent / events_name
    if not events_path.is_file():
        raise LoadReconciliationError("events file is missing")

    count = 0
    with events_path.open(encoding="utf-8") as stream:
        for line in stream:
            count += 1
            try:
                record = json.loads(line)
                metadata = record["metadata"]
                if not isinstance(record["source_feature"], dict) or any(
                    metadata[field] != manifest[field]
                    for field in ("logical_batch_id", "attempt_id", "fetched_at")
                ):
                    raise ValueError("record does not match manifest")
                for field in ("window_id", "payload_hash", "parser_version"):
                    if not metadata[field]:
                        raise ValueError(f"missing {field}")
            except (ValueError, KeyError, TypeError) as exc:
                raise LoadReconciliationError(f"invalid events row {count}: {exc}") from exc

    if not count == manifest.get("source_rows_returned") == manifest.get("raw_rows_written"):
        raise LoadReconciliationError("manifest and local events row counts disagree")
    return manifest, count


def reconcile_loaded_rows(expected: int, copy_rows: int, raw_rows: int) -> None:
    """Require both Snowflake counts to match the validated local attempt."""
    if min(expected, copy_rows, raw_rows) < 0 or expected != copy_rows or expected != raw_rows:
        raise LoadReconciliationError(
            f"row counts disagree (local={expected}, copied={copy_rows}, raw={raw_rows})"
        )


def plan_raw_load(manifest_path: Path) -> dict[str, Any]:
    """Build a read-only plan for one completed attempt; make no account calls."""
    manifest, row_count = validate_local_batch(manifest_path)
    attempt_id = manifest["attempt_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attempt_id):
        raise LoadReconciliationError("unsafe attempt ID for stage path")
    events_path = (manifest_path.parent / "events.jsonl").resolve()
    stage_path = f"@QUAKEWATCH.RAW.USGS_JSON_STAGE/{attempt_id}"
    copy_template = Path("sql/phase1_copy_raw.sql").read_text(encoding="utf-8")
    return {
        "attempt_id": attempt_id,
        "expected_rows": row_count,
        "events_path": str(events_path),
        "stage_path": stage_path,
        "put_sql": f"PUT '{events_path.as_uri()}' {stage_path} AUTO_COMPRESS=FALSE OVERWRITE=FALSE",
        "copy_sql": copy_template.replace("{{ attempt_id }}", attempt_id),
        "manifest": manifest,
    }


RECEIPT_SQL = """
INSERT INTO QUAKEWATCH.RAW.BATCH_ATTEMPT (
    ATTEMPT_ID, LOGICAL_BATCH_ID, BATCH_KIND, SITE_KEY,
    REQUESTED_STARTTIME, REQUESTED_ENDTIME, QUERY_PARAMETERS, WINDOW_AUDIT,
    COVERAGE_GAPS, FETCHED_AT, EXTRACT_STATUS, LOAD_STATUS,
    SOURCE_ROWS_RETURNED, RAW_ROWS_WRITTEN, LOADED_ROWS,
    STAGED_FILES, COPY_RESULTS, ERROR_TYPE, ERROR_MESSAGE, MANIFEST
)
SELECT %s, %s, 'origin', %s,
       TO_TIMESTAMP_TZ(%s), TO_TIMESTAMP_TZ(%s), PARSE_JSON(%s), PARSE_JSON(%s),
       PARSE_JSON(%s), TO_TIMESTAMP_TZ(%s), %s, %s,
       %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, %s, PARSE_JSON(%s)
"""


def append_receipt(cursor: Any, plan: dict[str, Any], status: str, loaded: int,
                   copy_results: list[dict[str, Any]], error: Exception | None = None) -> None:
    """Append one immutable outcome for this attempt."""
    manifest = plan["manifest"]
    site_name = manifest.get("site", {}).get("name", "")
    site_key = site_name.lower().replace(" ", "-") or None
    values = (
        manifest["attempt_id"], manifest["logical_batch_id"], site_key,
        manifest["requested_starttime"], manifest["requested_endtime"],
        json.dumps(manifest["query_parameters"]), json.dumps(manifest["window_audit"]),
        json.dumps(manifest.get("coverage_gaps", [])), manifest["fetched_at"],
        manifest["status"], status, manifest["source_rows_returned"],
        manifest["raw_rows_written"], loaded,
        json.dumps([plan["stage_path"] + "/events.jsonl"]),
        json.dumps(copy_results), type(error).__name__ if error else None,
        str(error) if error else None, json.dumps(manifest),
    )
    cursor.execute(RECEIPT_SQL, values)


def _result_dicts(cursor: Any) -> list[dict[str, Any]]:
    columns = [column.name.lower() for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def execute_raw_load(plan: dict[str, Any], connection: Any) -> int:
    """Upload and COPY one new attempt, then reconcile and append its receipt."""
    attempt_id = plan["attempt_id"]
    with closing(connection.cursor()) as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM QUAKEWATCH.RAW.BATCH_ATTEMPT WHERE ATTEMPT_ID = %s",
            (attempt_id,),
        )
        if cursor.fetchone()[0]:
            raise LoadReconciliationError("attempt already has an immutable receipt")
        cursor.execute(
            "SELECT COUNT(*) FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS WHERE ATTEMPT_ID = %s",
            (attempt_id,),
        )
        if cursor.fetchone()[0]:
            raise LoadReconciliationError("attempt already has RAW rows; investigate before retry")

        copy_results: list[dict[str, Any]] = []
        loaded = 0
        try:
            cursor.execute(plan["put_sql"])
            put_results = _result_dicts(cursor)
            if len(put_results) != 1 or put_results[0].get("status", "").upper() != "UPLOADED":
                raise LoadReconciliationError(f"stage upload did not upload one new file: {put_results}")
            cursor.execute(plan["copy_sql"])
            copy_results = _result_dicts(cursor)
            if len(copy_results) != 1 or copy_results[0].get("status", "").upper() != "LOADED":
                raise LoadReconciliationError(f"COPY did not load one file: {copy_results}")
            loaded = int(copy_results[0]["rows_loaded"])
            cursor.execute(
                "SELECT COUNT(*) FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS WHERE ATTEMPT_ID = %s",
                (attempt_id,),
            )
            raw_rows = int(cursor.fetchone()[0])
            reconcile_loaded_rows(plan["expected_rows"], loaded, raw_rows)
        except Exception as exc:
            append_receipt(cursor, plan, "failed", loaded, copy_results, exc)
            raise

        append_receipt(cursor, plan, "complete", loaded, copy_results)
        return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a RAW load plan from the repository root")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--execute", action="store_true", help="Connect and run PUT/COPY (warehouse cost)")
    args = parser.parse_args()
    plan = plan_raw_load(args.manifest)
    print(f"Attempt: {plan['attempt_id']}")
    print(f"Expected RAW rows: {plan['expected_rows']}")
    print(f"Local file: {plan['events_path']}")
    print(f"Stage path: {plan['stage_path']}")
    if not args.execute:
        print("No upload, COPY, or account connection performed.")
        return
    with closing(connect_project()) as connection:
        loaded = execute_raw_load(plan, connection)
    print(f"Loaded and reconciled RAW rows: {loaded}")


if __name__ == "__main__":
    main()
