"""Offline query-ID guard for the optional clone recovery drill."""

import unittest

from scripts.phase4_clone_recovery import before_query


class CloneRecoveryTests(unittest.TestCase):
    def test_accepts_snowflake_query_id(self) -> None:
        query_id = "01c76f7e-0002-b136-000e-fef2000380fa"
        self.assertIn(f"STATEMENT => '{query_id}'", before_query(query_id))

    def test_rejects_untrusted_query_id(self) -> None:
        for query_id in ("", "not-a-query", "abc'; DROP TABLE X; --"):
            with self.subTest(query_id=query_id):
                with self.assertRaises(ValueError):
                    before_query(query_id)
