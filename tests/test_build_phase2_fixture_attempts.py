"""Validate the four synthetic RAW attempts before any Snowflake load."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quakewatch.raw_load import validate_local_batch
from quakewatch.staging import project_feature
from scripts.fixtures.build_phase2_fixture_attempts import SEQUENCE, build_attempts


class FixtureAttemptsTest(unittest.TestCase):
    def test_four_attempts_have_distinct_lineage_and_synthetic_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summaries = build_attempts(root)
            self.assertEqual(
                [item["attempt_id"] for item in summaries], [item[0] for item in SEQUENCE]
            )
            self.assertEqual(build_attempts(root), summaries)
            updates = []
            for attempt_id, fixture_name in SEQUENCE:
                folder = root / attempt_id
                manifest, count = validate_local_batch(folder / "manifest.json")
                record = json.loads((folder / "events.jsonl").read_text())
                feature = record["source_feature"]
                fields = project_feature(feature)
                self.assertEqual(count, 1)
                self.assertTrue(manifest["fixture_only"])
                self.assertEqual(manifest["fixture_source"], fixture_name)
                self.assertEqual(manifest["query_parameters"]["source"], "local_synthetic_fixture")
                self.assertEqual(manifest["window_audit"][0]["status"], "synthetic_fixture")
                self.assertEqual(manifest["attempt_id"], record["metadata"]["attempt_id"])
                self.assertEqual(fields["source_event_id"], "uw714110682")
                self.assertIsNone(fields["reject_reason"])
                self.assertEqual(
                    record["metadata"]["payload_hash"],
                    hashlib.sha256(
                        json.dumps(
                            feature, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                        ).encode()
                    ).hexdigest(),
                )
                updates.append(fields["source_updated_at"])
            self.assertLess(updates[0], updates[1])
            self.assertLess(updates[1], updates[2])
            self.assertEqual(updates[0], updates[3])
            first = root / SEQUENCE[0][0]
            replay = root / SEQUENCE[3][0]
            first_manifest = json.loads((first / "manifest.json").read_text())
            replay_manifest = json.loads((replay / "manifest.json").read_text())
            first_record = json.loads((first / "events.jsonl").read_text())
            replay_record = json.loads((replay / "events.jsonl").read_text())
            self.assertNotEqual(first_manifest["attempt_id"], replay_manifest["attempt_id"])
            self.assertEqual(
                first_manifest["requested_starttime"], replay_manifest["requested_starttime"]
            )
            self.assertEqual(
                first_manifest["requested_endtime"], replay_manifest["requested_endtime"]
            )
            self.assertEqual(first_record["source_feature"], replay_record["source_feature"])
            self.assertEqual(
                first_record["metadata"]["payload_hash"], replay_record["metadata"]["payload_hash"]
            )

    def test_existing_different_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / SEQUENCE[0][0] / "manifest.json"
            path.parent.mkdir()
            path.write_text("keep me")
            with self.assertRaisesRegex(ValueError, "stop before overwrite"):
                build_attempts(root)
            self.assertEqual(path.read_text(), "keep me")


if __name__ == "__main__":
    unittest.main()
