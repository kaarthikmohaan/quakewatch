"""Check local old-origin revision fixtures and reconciled attempt files."""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from quakewatch.raw_load import validate_local_batch
from quakewatch.staging import project_feature
from scripts.build_phase2_fixture_attempts import build_attempts
from scripts.build_phase2_old_origin_attempts import FETCH_BASE, SEQUENCE


class OldOriginAttemptsTest(unittest.TestCase):
    def test_old_origin_update_is_outside_recent_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(len(build_attempts(root, SEQUENCE, FETCH_BASE)), 2)
            self.assertEqual(len(build_attempts(root, SEQUENCE, FETCH_BASE)), 2)
            rows = []
            for attempt_id, fixture in SEQUENCE:
                path = root / attempt_id
                manifest, count = validate_local_batch(path / "manifest.json")
                record = json.loads((path / "events.jsonl").read_text())
                self.assertEqual((count, manifest["fixture_source"], manifest["fixture_only"]),
                                 (1, fixture, True))
                self.assertEqual(manifest["requested_starttime"],
                                 "2020-01-15T00:00:00.000Z")
                self.assertEqual(manifest["requested_endtime"],
                                 "2020-01-16T00:00:00.000Z")
                self.assertEqual(record["metadata"]["attempt_id"], attempt_id)
                row = project_feature(record["source_feature"])
                self.assertIsNone(row["reject_reason"])
                rows.append(row)
            recent_start = datetime(2021, 9, 29, tzinfo=UTC)
            self.assertTrue(all(row["origin_time"] < recent_start for row in rows))
            self.assertEqual(rows[0]["source_event_id"], rows[1]["source_event_id"])
            self.assertEqual(rows[0]["origin_time"], rows[1]["origin_time"])
            self.assertLess(rows[0]["source_updated_at"], rows[1]["source_updated_at"])
            self.assertEqual([row["magnitude"] for row in rows], [1.1, 1.3])


if __name__ == "__main__":
    unittest.main()
