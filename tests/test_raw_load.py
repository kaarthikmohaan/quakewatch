"""Offline reconciliation tests for the RAW loader."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from quakewatch.raw_load import (
    LoadReconciliationError,
    execute_raw_load,
    plan_raw_load,
    project_connection_params,
    reconcile_loaded_rows,
    validate_local_batch,
)


class RawLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = {
            "status": "complete", "coverage_gaps": [], "events_file": "events.jsonl",
            "logical_batch_id": "logical", "attempt_id": "attempt",
            "fetched_at": "2026-09-29T00:00:00Z",
            "source_rows_returned": 1, "raw_rows_written": 1,
            "requested_starttime": "2026-09-28T00:00:00Z",
            "requested_endtime": "2026-09-29T00:00:00Z",
            "query_parameters": {"format": "geojson"},
            "window_audit": [{"window_id": "w0001", "status": "reconciled"}],
            "site": {"name": "Seattle"},
        }
        self.record = {
            "source_feature": {"id": "example"},
            "metadata": {
                "logical_batch_id": "logical", "attempt_id": "attempt",
                "fetched_at": "2026-09-29T00:00:00Z", "window_id": "w0001",
                "payload_hash": "a" * 64, "parser_version": "1",
            },
        }
        self.write_batch()

    def write_batch(self) -> None:
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.root / "events.jsonl").write_text(json.dumps(self.record) + "\n", encoding="utf-8")

    def test_matching_attempt_and_load_counts_pass(self) -> None:
        manifest, count = validate_local_batch(self.root / "manifest.json")
        self.assertEqual(manifest["attempt_id"], "attempt")
        self.assertEqual(count, 1)
        reconcile_loaded_rows(count, 1, 1)

    def test_unresolved_gap_blocks_load(self) -> None:
        self.manifest["coverage_gaps"] = [{"window_id": "w0001"}]
        self.write_batch()
        with self.assertRaisesRegex(LoadReconciliationError, "coverage gaps"):
            validate_local_batch(self.root / "manifest.json")

    def test_row_from_another_attempt_blocks_load(self) -> None:
        self.record["metadata"]["attempt_id"] = "other"
        self.write_batch()
        with self.assertRaisesRegex(LoadReconciliationError, "invalid events row 1"):
            validate_local_batch(self.root / "manifest.json")

    def test_missing_row_blocks_load(self) -> None:
        (self.root / "events.jsonl").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(LoadReconciliationError, "row counts disagree"):
            validate_local_batch(self.root / "manifest.json")

    def test_copy_or_raw_count_mismatch_blocks_success(self) -> None:
        with self.assertRaisesRegex(LoadReconciliationError, "copied=0"):
            reconcile_loaded_rows(1, 0, 1)
        with self.assertRaisesRegex(LoadReconciliationError, "raw=0"):
            reconcile_loaded_rows(1, 1, 0)

    def test_plan_uses_attempt_specific_stage_path(self) -> None:
        plan = plan_raw_load(self.root / "manifest.json")
        self.assertEqual(plan["expected_rows"], 1)
        self.assertEqual(plan["stage_path"], "@QUAKEWATCH.RAW.USGS_JSON_STAGE/attempt")
        self.assertIn("/attempt/events.jsonl", plan["copy_sql"])
        self.assertNotIn("{{ attempt_id }}", plan["copy_sql"])
        self.assertIn("AUTO_COMPRESS=FALSE OVERWRITE=FALSE", plan["put_sql"])

    def test_unsafe_attempt_id_blocks_plan(self) -> None:
        self.manifest["attempt_id"] = "bad/id"
        self.record["metadata"]["attempt_id"] = "bad/id"
        self.write_batch()
        with self.assertRaisesRegex(LoadReconciliationError, "unsafe attempt ID"):
            plan_raw_load(self.root / "manifest.json")

    def test_connection_uses_only_project_key_profile(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            '[connections.quakewatch_admin]\nrole="ACCOUNTADMIN"\npassword="unused"\n'
            '[connections.quakewatch_project]\naccount="example"\nuser="example_user"\n'
            'role="QUAKEWATCH_ROLE"\nauthenticator="SNOWFLAKE_JWT"\n'
            'private_key_file="/example/key.p8"\n',
            encoding="utf-8",
        )
        params = project_connection_params(config, "local-passphrase")
        self.assertEqual(params["role"], "QUAKEWATCH_ROLE")
        self.assertEqual(params["authenticator"], "SNOWFLAKE_JWT")
        self.assertEqual(params["private_key_file_pwd"], "local-passphrase")
        self.assertNotIn("password", params)

    def test_admin_role_in_project_profile_is_rejected(self) -> None:
        config = self.root / "config.toml"
        config.write_text(
            '[connections.quakewatch_project]\nrole="ACCOUNTADMIN"\n'
            'authenticator="SNOWFLAKE_JWT"\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(LoadReconciliationError, "QUAKEWATCH_ROLE"):
            project_connection_params(config, "local-passphrase")

    def test_successful_copy_appends_complete_receipt(self) -> None:
        cursor = FakeCursor()
        loaded = execute_raw_load(plan_raw_load(self.root / "manifest.json"), FakeConnection(cursor))
        self.assertEqual(loaded, 1)
        self.assertEqual(len(cursor.receipts), 1)
        self.assertEqual(cursor.receipts[0][10], "complete")
        self.assertEqual(cursor.receipts[0][13], 1)
        self.assertTrue(cursor.closed)

    def test_copy_failure_appends_failed_receipt(self) -> None:
        cursor = FakeCursor(copy_status="LOAD_FAILED")
        with self.assertRaisesRegex(LoadReconciliationError, "COPY did not load"):
            execute_raw_load(plan_raw_load(self.root / "manifest.json"), FakeConnection(cursor))
        self.assertEqual(len(cursor.receipts), 1)
        self.assertEqual(cursor.receipts[0][10], "failed")
        self.assertEqual(cursor.receipts[0][16], "LoadReconciliationError")

    def test_existing_attempt_receipt_blocks_mutation(self) -> None:
        cursor = FakeCursor(existing_receipts=1)
        with self.assertRaisesRegex(LoadReconciliationError, "immutable receipt"):
            execute_raw_load(plan_raw_load(self.root / "manifest.json"), FakeConnection(cursor))
        self.assertEqual(len(cursor.commands), 1)

    def test_raw_count_mismatch_appends_failed_receipt(self) -> None:
        cursor = FakeCursor(raw_count_after=0)
        with self.assertRaisesRegex(LoadReconciliationError, "raw=0"):
            execute_raw_load(plan_raw_load(self.root / "manifest.json"), FakeConnection(cursor))
        self.assertEqual(cursor.receipts[0][10], "failed")
        self.assertEqual(cursor.receipts[0][13], 1)

    def test_existing_raw_rows_block_mutation(self) -> None:
        cursor = FakeCursor(raw_count_before=1)
        with self.assertRaisesRegex(LoadReconciliationError, "already has RAW rows"):
            execute_raw_load(plan_raw_load(self.root / "manifest.json"), FakeConnection(cursor))
        self.assertEqual(len(cursor.commands), 2)


class FakeConnection:
    def __init__(self, cursor: "FakeCursor") -> None:
        self._cursor = cursor

    def cursor(self) -> "FakeCursor":
        return self._cursor


class FakeCursor:
    def __init__(self, copy_status: str = "LOADED", existing_receipts: int = 0,
                 raw_count_before: int = 0, raw_count_after: int = 1) -> None:
        self.copy_status = copy_status
        self.existing_receipts = existing_receipts
        self.raw_count_before = raw_count_before
        self.raw_count_after = raw_count_after
        self.commands: list[str] = []
        self.receipts: list[tuple] = []
        self.raw_count_calls = 0
        self.description = []
        self.rows: list[tuple] = []
        self.closed = False

    def execute(self, sql: str, params: tuple | None = None) -> "FakeCursor":
        self.commands.append(sql)
        if "FROM QUAKEWATCH.RAW.BATCH_ATTEMPT WHERE" in sql:
            self.rows = [(self.existing_receipts,)]
        elif "FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS WHERE" in sql:
            self.raw_count_calls += 1
            self.rows = [(
                self.raw_count_before if self.raw_count_calls == 1 else self.raw_count_after,
            )]
        elif sql.startswith("PUT "):
            self.description = [SimpleNamespace(name="status")]
            self.rows = [("UPLOADED",)]
        elif "COPY INTO QUAKEWATCH.RAW.RAW_EVENT_RECORDS" in sql:
            self.description = [SimpleNamespace(name="status"), SimpleNamespace(name="rows_loaded")]
            self.rows = [(self.copy_status, 1 if self.copy_status == "LOADED" else 0)]
        elif "INSERT INTO QUAKEWATCH.RAW.BATCH_ATTEMPT" in sql:
            assert params is not None
            self.receipts.append(params)
            self.rows = []
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")
        return self

    def fetchone(self) -> tuple:
        return self.rows.pop(0)

    def fetchall(self) -> list[tuple]:
        rows, self.rows = self.rows, []
        return rows

    def close(self) -> None:
        self.closed = True
