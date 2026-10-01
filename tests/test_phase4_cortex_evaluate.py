"""Offline checks for bounded Cortex evaluation and SQL fallback."""

import tempfile
import unittest
from pathlib import Path

from scripts.phase4_cortex_evaluate import (
    MODEL, check_brief, pending_cases, prompt_for, read_cache, retry_case,
    write_cache,
)


def sample_case(case_id: str = "anchorage-2022") -> dict:
    return {
        "CASE_ID": case_id,
        "SITE_KEY": "anchorage",
        "START_UTC": "2022-01-01T00:00:00Z",
        "END_UTC": "2023-01-01T00:00:00Z",
        "RADIUS_KM": 250.0,
        "EVENT_COUNT": 22056,
        "NEAREST_EVENT_ID": "ak022f92oae2",
        "NEAREST_DISTANCE_KM": 0.9,
        "NEAREST_MAGNITUDE": 1.4,
        "NEAREST_SOURCE_STATUS": "reviewed",
        "NEAREST_RECORD_AGE_HOURS": 33248.0,
        "INPUT_SHA256": "aggregate-hash",
    }


class CortexEvaluateTests(unittest.TestCase):
    def test_prompt_and_strict_fact_check(self) -> None:
        case = sample_case()
        prompt = prompt_for(case)
        self.assertLessEqual(len(prompt), 1200)
        self.assertNotIn("latitude", prompt.lower())
        self.assertNotIn("longitude", prompt.lower())

        brief = (
            "In the modeled Anchorage sample for 2022, 22,056 events were within "
            "250 km; the nearest event ak022f92oae2 was 0.9 km from Anchorage, "
            "magnitude 1.4, source status reviewed, and its source record was "
            "33248.0 hours old at the SQL check time."
        )
        self.assertEqual(check_brief(brief, case), [])
        self.assertIn("missing or misstated distance", check_brief(
            brief.replace("from Anchorage", "from ak022f92oae2"), case,
        ))
        self.assertIn("hazard or action language", check_brief(brief + " Shaking risk.", case))

    def test_cache_skips_existing_and_seattle_day(self) -> None:
        cases = [sample_case(), sample_case("seattle-day")]
        cache = {"model": MODEL, "results": {}}
        self.assertEqual(pending_cases(cases, cache), cases[:1])

        cache["results"]["aggregate-hash"] = {"status": "rejected"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "briefs.json"
            write_cache(cache, path)
            loaded = read_cache(path)
        self.assertEqual(pending_cases(cases, loaded), [])
        self.assertEqual(retry_case(cases, loaded, "anchorage-2022")["CASE_ID"],
                         "anchorage-2022")
        loaded["results"]["aggregate-hash"]["retry"] = {"status": "attempt_started"}
        with self.assertRaisesRegex(RuntimeError, "already used"):
            retry_case(cases, loaded, "anchorage-2022")
