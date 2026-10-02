"""Mock the procedure entry point without importing local Snowpark."""

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from quakewatch.process_transaction import ProcessOutcome
from quakewatch.snowpark_alias_read import resolve_durable_aliases
from quakewatch.snowpark_model_writer import SnowparkModelWriter
from quakewatch.snowpark_procedure import run

TIME = datetime(2026, 9, 30, tzinfo=UTC)


class ProcedureEntryTest(unittest.TestCase):
    @patch("quakewatch.snowpark_procedure.process_loaded_attempt")
    def test_handler_returns_committed_outcome(self, process):
        process.return_value = ProcessOutcome(
            "process-1", "attempt-1", TIME, TIME, "complete", 3, 3, 1, 2
        )
        session = object()
        result = json.loads(run(session, "attempt-1"))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(
            (
                result["loaded_rows"],
                result["processed_rows"],
                result["rejected_rows"],
                result["revision_rows_merged"],
            ),
            (3, 3, 1, 2),
        )
        args = process.call_args.args
        self.assertIs(args[0], session)
        self.assertEqual(args[1], "attempt-1")
        self.assertIsInstance(args[2], SnowparkModelWriter)
        self.assertIs(args[2].canonical_resolver, resolve_durable_aliases)

    @patch(
        "quakewatch.snowpark_procedure.process_loaded_attempt",
        side_effect=ValueError("load receipt incomplete"),
    )
    def test_handler_propagates_failure(self, process):
        with self.assertRaisesRegex(ValueError, "load receipt incomplete"):
            run(object(), "attempt-1")


if __name__ == "__main__":
    unittest.main()
