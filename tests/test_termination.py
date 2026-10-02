"""A terminated capture is recorded as failed instead of staying 'running'."""

import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from quakewatch import extract_batch

ROOT = Path(__file__).resolve().parents[1]


class TerminationTest(unittest.TestCase):
    def test_sigterm_handler_raises_keyboard_interrupt(self):
        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        extract_batch.install_termination_handler()
        with self.assertRaises(KeyboardInterrupt):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    def test_main_reports_interruption_with_exit_130(self):
        argv = [
            "quakewatch-extract",
            "--site",
            "seattle",
            "--start",
            "2026-09-27",
            "--end",
            "2026-09-28",
        ]
        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        with (
            patch("sys.argv", argv),
            patch.object(
                extract_batch, "run_batch", side_effect=KeyboardInterrupt("terminated by signal 15")
            ),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            self.assertEqual(extract_batch.main(), 130)
        self.assertIn("manifest marked failed", err.getvalue())

    def test_real_sigterm_leaves_a_failed_manifest(self):
        with tempfile.TemporaryDirectory() as out:
            env = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "HTTP_PROXY": "http://127.0.0.1:9",
            }
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "quakewatch.extract_batch",
                    "--site",
                    "seattle",
                    "--start",
                    "2026-09-27T00:00:00Z",
                    "--end",
                    "2026-09-28T00:00:00Z",
                    "--output",
                    out,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 10
            while not list(Path(out).glob("*/manifest.json")) and time.monotonic() < deadline:
                time.sleep(0.05)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=20), 130)
            manifest = json.loads(next(Path(out).glob("*/manifest.json")).read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["error_type"], "KeyboardInterrupt")


if __name__ == "__main__":
    unittest.main()
