"""The interrupted recovery drill diagnostic stays read-only."""

import contextlib
import inspect
import io
import unittest
from unittest.mock import patch

from scripts.evidence.phase2 import first_failure_state


class FirstFailureStateTest(unittest.TestCase):
    def test_preview_does_not_connect(self):
        output = io.StringIO()
        with patch("scripts.evidence.phase2.first_failure_state.connect_project",
                   side_effect=AssertionError("connected")), \
             patch("sys.argv", ["first_failure_state.py"]), \
             contextlib.redirect_stdout(output):
            first_failure_state.main()
        self.assertIn("no Snowflake connection", output.getvalue())

    def test_live_function_has_only_selects_and_session_setup(self):
        source = inspect.getsource(first_failure_state.execute).upper()
        for write in ("INSERT INTO", "DELETE FROM", "MERGE INTO", "CREATE ", "CALL "):
            self.assertNotIn(write, source)
        self.assertIn("SELECT COUNT(*)", source)


if __name__ == "__main__":
    unittest.main()
