"""Mock the model writer call order without Snowflake compute."""

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from quakewatch.process_batch import BatchProjection
from quakewatch.process_transaction import ProcessOutcome
from quakewatch.snowpark_model_writer import SnowparkModelWriter

TIME = datetime(2026, 9, 30, tzinfo=UTC)
PROJECTION = BatchProjection("attempt-1", 2, 2, 1, ())
SUCCESS = ProcessOutcome("process-1", "attempt-1", TIME, TIME, "complete", 2, 2, 1, 1)
FAILURE = ProcessOutcome(
    "process-2", "attempt-1", TIME, TIME, "failed", 2, 2, 1, 0, "ValueError", "bad model"
)


class ModelWriterTest(unittest.TestCase):
    @patch("quakewatch.snowpark_model_writer.append_process_outcome")
    @patch("quakewatch.snowpark_model_writer.write_successful_batch_fact")
    @patch("quakewatch.snowpark_model_writer.write_dimensions_and_bridge")
    @patch("quakewatch.snowpark_model_writer.write_revision_fact", return_value=1)
    @patch("quakewatch.snowpark_model_writer.rekey_existing_aliases")
    @patch("quakewatch.snowpark_model_writer.write_staging")
    def test_models_then_batch_fact_then_success_log(
        self, staging, rekey, revision, bridge, batch, log
    ):
        events = []
        for name, mock in (
            ("staging", staging),
            ("rekey", rekey),
            ("revision", revision),
            ("bridge", bridge),
            ("batch", batch),
            ("log", log),
        ):
            mock.side_effect = lambda *args, name=name: (
                events.append(name) or (1 if name == "revision" else None)
            )

        def resolve(session, projection):
            events.append("aliases")
            return {"id-1": "canonical-1"}

        writer = SnowparkModelWriter(resolve)
        self.assertEqual(writer.write_models(object(), PROJECTION), 1)
        writer.record_success(object(), SUCCESS)
        self.assertEqual(
            events, ["staging", "aliases", "rekey", "revision", "bridge", "batch", "log"]
        )

    @patch("quakewatch.snowpark_model_writer.append_process_outcome")
    def test_failure_only_appends_log(self, log):
        writer = SnowparkModelWriter(lambda _session, _projection: {})
        writer.record_failure(object(), FAILURE)
        log.assert_called_once()

    def test_success_without_projection_is_rejected(self):
        writer = SnowparkModelWriter(lambda _session, _projection: {})
        with self.assertRaisesRegex(ValueError, "lacks its completed"):
            writer.record_success(object(), SUCCESS)

    @patch("quakewatch.snowpark_model_writer.write_staging")
    @patch("quakewatch.snowpark_model_writer.rekey_existing_aliases")
    @patch(
        "quakewatch.snowpark_model_writer.write_revision_fact",
        side_effect=ValueError("alias rekey required"),
    )
    def test_rekey_conflict_does_not_continue_to_bridge(self, revision, rekey, staging):
        writer = SnowparkModelWriter(lambda _session, _projection: {})
        with patch("quakewatch.snowpark_model_writer.write_dimensions_and_bridge") as bridge:
            with self.assertRaisesRegex(ValueError, "alias rekey required"):
                writer.write_models(object(), PROJECTION)
            bridge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
