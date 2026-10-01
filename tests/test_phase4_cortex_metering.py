"""Offline guard for bounded Cortex metering query IDs."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.phase4_cortex_metering import (
    EARLIER_SUCCESSFUL_QUERY_IDS, expected_query_ids,
)


class CortexMeteringTests(unittest.TestCase):
    def test_collects_exactly_eleven_unique_successful_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "briefs.json"
            path.write_text(json.dumps({"results": {
                str(index): {"query_id": f"new-query-{index}"}
                for index in range(9)
            }}))
            ids = expected_query_ids(path)

        self.assertEqual(len(ids), 11)
        self.assertEqual(ids[:2], list(EARLIER_SUCCESSFUL_QUERY_IDS))

    def test_rejects_incomplete_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "briefs.json"
            path.write_text(json.dumps({"results": {}}))
            with self.assertRaisesRegex(RuntimeError, "eleven unique"):
                expected_query_ids(path)
