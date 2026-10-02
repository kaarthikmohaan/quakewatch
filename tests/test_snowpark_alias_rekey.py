"""Mock canonical rekey preflight and fact/bridge update order."""

import unittest
from datetime import UTC, datetime

from quakewatch.snowpark_alias_rekey import rekey_existing_aliases

TIME = datetime(2026, 9, 30, tzinfo=UTC)


class FakeRow:
    def __init__(self, values):
        self.values = values

    def as_dict(self):
        return self.values


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return [FakeRow(row) for row in self.rows]


class FakeSession:
    def __init__(self, facts, bridges=(), wrong_count=False):
        self.facts = list(facts)
        self.bridges = list(bridges)
        self.wrong_count = wrong_count
        self.calls = []

    def sql(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT CANONICAL_EVENT_ID, SOURCE_EVENT_ID" in query:
            return FakeFrame(self.facts)
        if "SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT" in query:
            return FakeFrame(self.bridges)
        if "DELETE FROM" in query:
            rows = self.bridges if "BRIDGE_EVENT_SITE" in query else self.facts
            matched = [
                row
                for row in rows
                if (
                    row["CANONICAL_EVENT_ID"],
                    row["SOURCE_UPDATED_AT"].isoformat(),
                    row["PAYLOAD_HASH"],
                )
                == tuple(params)
            ]
            for row in matched:
                rows.remove(row)
            count = len(matched) + (1 if self.wrong_count else 0)
            return FakeFrame([{"number of rows deleted": count}])
        if "UPDATE " in query:
            rows = self.bridges if "BRIDGE_EVENT_SITE" in query else self.facts
            matched = [row for row in rows if row["CANONICAL_EVENT_ID"] == params[1]]
            for row in matched:
                row["CANONICAL_EVENT_ID"] = params[0]
            count = len(matched) + (1 if self.wrong_count else 0)
            return FakeFrame([{"number of rows updated": count}])
        return FakeFrame([])


def fact(canonical, source, hash_value="a", fetched_at=TIME, stage_file_name="events.jsonl"):
    return {
        "CANONICAL_EVENT_ID": canonical,
        "SOURCE_EVENT_ID": source,
        "SOURCE_UPDATED_AT": TIME,
        "PAYLOAD_HASH": hash_value,
        "FETCHED_AT": fetched_at,
        "STAGE_FILE_NAME": stage_file_name,
        "STAGE_FILE_ROW_NUMBER": 1,
    }


def bridge(canonical, hash_value="a", site="seattle"):
    return {
        "CANONICAL_EVENT_ID": canonical,
        "SOURCE_UPDATED_AT": TIME,
        "PAYLOAD_HASH": hash_value,
        "SITE_KEY": site,
    }


def all_sites(canonical, hash_value="a"):
    return [
        bridge(canonical, hash_value, site) for site in ("seattle", "san-francisco", "anchorage")
    ]


class AliasRekeyTest(unittest.TestCase):
    def test_new_alias_moves_fact_and_bridge_together(self):
        session = FakeSession([fact("z", "z")], [bridge("z")])
        self.assertEqual(rekey_existing_aliases(session, {"z": "a"}), 1)
        updates = [(sql, params) for sql, params in session.calls if "UPDATE " in sql]
        self.assertEqual(len(updates), 2)
        self.assertIn("FACT_EVENT_REVISION", updates[0][0])
        self.assertIn("BRIDGE_EVENT_SITE", updates[1][0])
        self.assertEqual(updates[0][1], ["a", "z"])

    def test_collision_keeps_latest_fetch_and_its_site_rows(self):
        later = TIME.replace(hour=1)
        session = FakeSession(
            [fact("z", "z", fetched_at=later), fact("a", "a")], all_sites("z") + all_sites("a")
        )
        self.assertEqual(rekey_existing_aliases(session, {"z": "a", "a": "a"}), 1)
        writes = [
            (sql, params)
            for sql, params in session.calls
            if "DELETE FROM" in sql or "UPDATE " in sql
        ]
        self.assertEqual(len(writes), 4)
        self.assertIn("DELETE FROM QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE", writes[0][0])
        self.assertIn("DELETE FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION", writes[1][0])
        self.assertEqual(writes[0][1][0], "a")
        self.assertIn("TO_TIMESTAMP_TZ(?)", writes[0][0])
        self.assertEqual(writes[2][1], ["a", "z"])

    def test_collision_without_survivor_bridge_stops_before_write(self):
        session = FakeSession(
            [fact("z", "z", fetched_at=TIME.replace(hour=1)), fact("a", "a")],
            [bridge("z"), bridge("a")],
        )
        with self.assertRaisesRegex(ValueError, "complete public-site bridge"):
            rekey_existing_aliases(session, {"z": "a", "a": "a"})
        self.assertFalse(any("UPDATE " in sql or "DELETE FROM" in sql for sql, _ in session.calls))

    def test_duplicate_original_revision_stops_before_write(self):
        session = FakeSession([fact("z", "z"), fact("z", "z")])
        with self.assertRaisesRegex(ValueError, "duplicate existing revision"):
            rekey_existing_aliases(session, {"z": "a"})
        self.assertEqual(len(session.calls), 1)

    def test_unexpected_dml_row_count_stops_transaction(self):
        session = FakeSession([fact("z", "z")], [bridge("z")], wrong_count=True)
        with self.assertRaisesRegex(ValueError, "count differs from preflight"):
            rekey_existing_aliases(session, {"z": "a"})

    def test_missing_source_alias_stops(self):
        with self.assertRaisesRegex(ValueError, "missing from durable"):
            rekey_existing_aliases(FakeSession([fact("z", "z")]), {})

    def test_same_key_needs_no_bridge_read_or_update(self):
        session = FakeSession([fact("a", "a")])
        self.assertEqual(rekey_existing_aliases(session, {"a": "a"}), 0)
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
