"""
logging.py – Structured logging setup for the fundamental engine.

Provides a factory function that returns properly configured loggers.
Use ``get_logger(__name__)`` at the top of every module.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """
    Configure root logger for the entire engine.

    Call once at application entrypoint (CLI or script).

    Parameters
    ----------
    level:
        Logging level string: DEBUG, INFO, WARNING, ERROR.
    json_output:
        If True, emit JSON-structured log lines (useful for log aggregation).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if json_output:
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger("fundamental_engine")
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger scoped within the fundamental_engine namespace.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.

    Returns
    -------
    logging.Logger
    """
    if not name.startswith("fundamental_engine"):
        name = f"fundamental_engine.{name}"
    return logging.getLogger(name)


class _JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter for structured output."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        import datetime

        payload = {
            "ts": datetime.datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)
