"""Offline checks for the bounded Cortex prompt."""

import unittest

from scripts.evidence.phase4.cortex_trial import prompt_for, validate_brief


class CortexTrialTests(unittest.TestCase):
    def test_prompt_contains_sql_facts_without_coordinates(self) -> None:
        prompt = prompt_for({
            "event_count": 15,
            "nearest_event_id": "us-test-1",
            "nearest_distance_km": 12.3,
            "nearest_magnitude": 1.2,
            "nearest_source_status": "reviewed",
            "nearest_age_hours": 48.0,
        })

        self.assertIn("count=15", prompt)
        self.assertIn("nearest ID=us-test-1", prompt)
        self.assertIn("nearest source status=reviewed", prompt)
        self.assertIn("not complete coverage", prompt)
        self.assertNotIn("longitude", prompt.lower())
        self.assertNotIn("latitude", prompt.lower())
        self.assertLessEqual(len(prompt), 1200)

    def test_rejects_observed_invented_radius_and_truncation(self) -> None:
        facts = {
            "event_count": 15,
            "nearest_event_id": "uw714111042",
            "nearest_distance_km": 42.1,
            "nearest_magnitude": 1.23,
            "nearest_source_status": "reviewed",
            "nearest_age_hours": 59.8,
        }
        message = (
            "Number of Events within 15 km Radius: 15. "
            "Nearest uw714111042, 42.1 km, magnitude 1.23, reviewed. "
            "Time Since Last Update: "
        )

        self.assertEqual(validate_brief(message, facts), [
            "missing nearest_age_hours",
            "unsupported radius size",
            "incomplete ending",
        ])

    def test_rejects_distance_from_own_event_id(self) -> None:
        facts = {
            "event_count": 15,
            "nearest_event_id": "uw714111042",
            "nearest_distance_km": 42.1,
            "nearest_magnitude": 1.23,
            "nearest_source_status": "reviewed",
            "nearest_age_hours": 59.8,
        }
        message = (
            "Seattle modeled sample: 15 events; nearest is 42.1 km away from "
            "uw714111042, magnitude 1.23, reviewed, age 59.8 hours."
        )

        self.assertEqual(validate_brief(message, facts),
                         ["distance incorrectly anchored to event ID"])
