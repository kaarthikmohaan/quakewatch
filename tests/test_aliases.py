"""Canonical-ID grouping cases for preferred-ID changes and chained aliases."""

import unittest

from quakewatch.aliases import AliasObservation, canonical_id_map


class AliasResolutionTest(unittest.TestCase):
    def test_preferred_id_change_keeps_one_canonical_event(self) -> None:
        old = AliasObservation("us-old", ("us-old", "us-new"))
        new = AliasObservation("us-new", ("us-old", "us-new"))
        self.assertEqual(
            canonical_id_map([old, new]),
            {"us-new": "us-new", "us-old": "us-new"},
        )

    def test_transitive_aliases_and_input_order(self) -> None:
        first = AliasObservation("c", ("b",))
        second = AliasObservation("b", ("a",))
        expected = {"a": "a", "b": "a", "c": "a"}
        self.assertEqual(canonical_id_map([first, second]), expected)
        self.assertEqual(canonical_id_map([second, first]), expected)

    def test_unrelated_events_stay_separate(self) -> None:
        self.assertEqual(
            canonical_id_map([AliasObservation("x"), AliasObservation("y")]),
            {"x": "x", "y": "y"},
        )

    def test_bad_associated_id_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            canonical_id_map([AliasObservation("x", ("",))])

    def test_new_alias_can_change_canonical_key(self) -> None:
        before = canonical_id_map([AliasObservation("b")])
        after = canonical_id_map([AliasObservation("b", ("a",))])
        self.assertEqual(before["b"], "b")
        self.assertEqual(after["b"], "a")


if __name__ == "__main__":
    unittest.main()
