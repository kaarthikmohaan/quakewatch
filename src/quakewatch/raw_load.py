"""Local safeguards before and after a Snowflake RAW copy."""

import json
import re
import argparse
import getpass
import tomllib
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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a RAW load plan from the repository root")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    plan = plan_raw_load(args.manifest)
    print(f"Attempt: {plan['attempt_id']}")
    print(f"Expected RAW rows: {plan['expected_rows']}")
    print(f"Local file: {plan['events_path']}")
    print(f"Stage path: {plan['stage_path']}")
    print("No upload, COPY, or account connection performed.")


if __name__ == "__main__":
    main()
