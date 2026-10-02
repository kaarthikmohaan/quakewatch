"""The parser version 2 migration changes nothing unless every check passes."""

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.migrations import parser_v2 as release


class FakeCursor:
    """Answers the migration's queries from a small in-memory state."""

    def __init__(
        self,
        state,
        facts,
        stubs=release.EXPECTED_STUB_ROWS,
        placeholders=0,
        relabel_rows=release.EXPECTED_STUB_ROWS,
    ):
        self.state, self.facts = dict(state), dict(facts)
        self.stubs, self.placeholders, self.relabel_rows = stubs, placeholders, relabel_rows
        self.statements, self.rowcount, self._result = [], -1, []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if sql == release.STATE_SQL:
            self._result = [(v, r, c) for (v, r), c in self.state.items()]
        elif sql == release.FACT_STATE_SQL:
            self._result = list(self.facts.items())
        elif sql == release.STUB_SQL:
            self._result = [(self.stubs,)]
        elif sql == release.PLACEHOLDER_SQL:
            self._result = [(self.placeholders,)]
        elif sql == release.RELABEL_SQL:
            self.rowcount = self.relabel_rows
            moved = self.state.pop(("1", release.OLD_REASON), 0)
            self.state[("1", release.NEW_REASON)] = moved
        elif sql == release.STG_VERSION_SQL:
            self.rowcount = sum(self.state.values())
            self.state = {("2", r): c for (_, r), c in self.state.items()}
        elif sql == release.FACT_VERSION_SQL:
            self.rowcount = self.facts.pop("1", 0)
            self.facts["2"] = self.rowcount

    def fetchone(self):
        return self._result[0]

    def fetchall(self):
        return self._result


OLD = release.expected_state("1", release.OLD_REASON)
NEW = release.expected_state("2", release.NEW_REASON)


class MigrationTest(unittest.TestCase):
    def test_success_relabels_versions_and_commits(self):
        cursor = FakeCursor(OLD, {"1": 200_000})
        result = release.migrate(cursor)
        self.assertIn("relabelled 485", result)
        self.assertEqual(cursor.state, NEW)
        self.assertEqual(cursor.facts, {"2": 200_000})
        self.assertEqual(cursor.statements[-1], "COMMIT")

    def test_already_migrated_changes_nothing(self):
        cursor = FakeCursor(NEW, {"2": 200_000})
        self.assertEqual(release.migrate(cursor), "already migrated")
        self.assertNotIn("BEGIN", cursor.statements)

    def test_unexpected_state_stops_before_transaction(self):
        cursor = FakeCursor({("1", None): 10}, {"1": 10})
        with self.assertRaises(RuntimeError):
            release.migrate(cursor)
        self.assertNotIn("BEGIN", cursor.statements)

    def test_non_stub_reject_stops_before_transaction(self):
        cursor = FakeCursor(OLD, {"1": 10}, stubs=484)
        with self.assertRaises(RuntimeError):
            release.migrate(cursor)
        self.assertNotIn("BEGIN", cursor.statements)

    def test_valid_placeholder_row_stops_before_transaction(self):
        cursor = FakeCursor(OLD, {"1": 10}, placeholders=1)
        with self.assertRaises(RuntimeError):
            release.migrate(cursor)
        self.assertNotIn("BEGIN", cursor.statements)

    def test_wrong_update_count_rolls_back(self):
        cursor = FakeCursor(OLD, {"1": 10}, relabel_rows=480)
        with self.assertRaises(RuntimeError):
            release.migrate(cursor)
        self.assertEqual(cursor.statements[-1], "ROLLBACK")
        self.assertNotIn("COMMIT", cursor.statements)

    def test_stub_condition_requires_all_three_fields_missing(self):
        for key in ("time", "mag", "status"):
            self.assertIn(f"IS_NULL_VALUE(r.PAYLOAD:properties:{key})", release.STUB_CONDITION)

    def test_preview_does_not_connect(self):
        with (
            patch.object(release, "connect_project") as connect,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            release.preview()
        connect.assert_not_called()
        self.assertIn("preview only", out.getvalue())


if __name__ == "__main__":
    unittest.main()
