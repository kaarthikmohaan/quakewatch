"""Command logging goes to stderr with a configurable level."""

import logging
import os
import unittest
from unittest.mock import patch

from quakewatch.logs import LOG_LEVEL_ENV, configure_logging


class ConfigureLoggingTest(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        self.saved = (root.level, root.handlers[:])
        root.handlers.clear()

    def tearDown(self):
        root = logging.getLogger()
        root.handlers[:] = self.saved[1]
        root.setLevel(self.saved[0])

    def test_default_level_is_info(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_environment_overrides_level(self):
        with patch.dict(os.environ, {LOG_LEVEL_ENV: "debug"}):
            configure_logging()
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_http_client_request_logs_are_quiet(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_logging()
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)

    def test_timestamps_are_utc(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_logging()
        formatter = logging.getLogger().handlers[0].formatter
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "m", None, None)
        record.created = 0.0
        self.assertTrue(
            formatter.formatTime(record, formatter.datefmt).startswith("1970-01-01T00:00:00Z")
        )

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError):
            configure_logging("loud")


if __name__ == "__main__":
    unittest.main()
