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
    def __init__(self, facts, bridges=()):
        self.facts = facts
        self.bridges = bridges
        self.calls = []

    def sql(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT CANONICAL_EVENT_ID, SOURCE_EVENT_ID" in query:
            return FakeFrame(self.facts)
        if "SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT" in query:
            return FakeFrame(self.bridges)
        return FakeFrame([])


def fact(canonical, source, hash_value="a"):
    return {"CANONICAL_EVENT_ID": canonical, "SOURCE_EVENT_ID": source,
            "SOURCE_UPDATED_AT": TIME, "PAYLOAD_HASH": hash_value}


def bridge(canonical, hash_value="a", site="seattle"):
    return {"CANONICAL_EVENT_ID": canonical, "SOURCE_UPDATED_AT": TIME,
            "PAYLOAD_HASH": hash_value, "SITE_KEY": site}


class AliasRekeyTest(unittest.TestCase):
    def test_new_alias_moves_fact_and_bridge_together(self):
        session = FakeSession([fact("z", "z")], [bridge("z")])
        self.assertEqual(rekey_existing_aliases(session, {"z": "a"}), 1)
        updates = [(sql, params) for sql, params in session.calls if "UPDATE " in sql]
        self.assertEqual(len(updates), 2)
        self.assertIn("FACT_EVENT_REVISION", updates[0][0])
        self.assertIn("BRIDGE_EVENT_SITE", updates[1][0])
        self.assertEqual(updates[0][1], ["a", "z"])

    def test_revision_collision_stops_before_write(self):
        session = FakeSession([fact("z", "z"), fact("a", "a")])
        with self.assertRaisesRegex(ValueError, "revision key"):
            rekey_existing_aliases(session, {"z": "a", "a": "a"})
        self.assertFalse(any("UPDATE " in sql for sql, _ in session.calls))

    def test_bridge_collision_stops_before_write(self):
        session = FakeSession([fact("z", "z"), fact("a", "a", "b")],
                              [bridge("z"), bridge("a")])
        with self.assertRaisesRegex(ValueError, "bridge key"):
            rekey_existing_aliases(session, {"z": "a", "a": "a"})
        self.assertFalse(any("UPDATE " in sql for sql, _ in session.calls))

    def test_missing_source_alias_stops(self):
        with self.assertRaisesRegex(ValueError, "missing from durable"):
            rekey_existing_aliases(FakeSession([fact("z", "z")]), {})

    def test_same_key_needs_no_bridge_read_or_update(self):
        session = FakeSession([fact("a", "a")])
        self.assertEqual(rekey_existing_aliases(session, {"a": "a"}), 0)
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
