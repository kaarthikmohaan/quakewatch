"""Shared logging setup for QuakeWatch command-line tools.

Commands print their results to stdout. Operational events such as retries,
window splits, reconciliation failures, and commits go to the standard
``logging`` module, which this module sends to stderr with timestamps.
"""

from __future__ import annotations

import logging
import os
import time

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# Third-party clients log every HTTP request at INFO; keep only their warnings.
QUIET_LOGGERS = ("httpx", "httpcore", "snowflake.connector")
LOG_LEVEL_ENV = "QUAKEWATCH_LOG_LEVEL"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once; ``QUAKEWATCH_LOG_LEVEL`` overrides INFO."""
    name = (level or os.environ.get(LOG_LEVEL_ENV) or "INFO").upper()
    resolved = logging.getLevelName(name)
    if not isinstance(resolved, int):
        raise ValueError(f"unknown log level: {name}")
    handler = logging.StreamHandler()
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    formatter.converter = time.gmtime  # timestamps in UTC, like the data
    handler.setFormatter(formatter)
    logging.basicConfig(level=resolved, handlers=[handler])
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(resolved, logging.WARNING))
