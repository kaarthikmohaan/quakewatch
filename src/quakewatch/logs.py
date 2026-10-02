"""Shared logging setup for QuakeWatch command-line tools.

Commands print their results to stdout. Operational events such as retries,
window splits, reconciliation failures, and commits go to the standard
``logging`` module, which this module sends to stderr with timestamps.
"""

from __future__ import annotations

import logging
import os

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_LEVEL_ENV = "QUAKEWATCH_LOG_LEVEL"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once; ``QUAKEWATCH_LOG_LEVEL`` overrides INFO."""
    name = (level or os.environ.get(LOG_LEVEL_ENV) or "INFO").upper()
    resolved = logging.getLevelName(name)
    if not isinstance(resolved, int):
        raise ValueError(f"unknown log level: {name}")
    logging.basicConfig(level=resolved, format=LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z")
