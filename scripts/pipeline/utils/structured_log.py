"""structured_log.py — Structured JSON logging for observable skill execution.

Provides a thin wrapper around Python's logging module that emits JSON-formatted
log records to stdout. Each record includes level, logger name, and message, plus
any extra keyword arguments passed at the call site.

Concurrency:
    get_logger() is safe to call from multiple threads. The returned Logger instance
    uses a StreamHandler; Python's logging module handles thread-safe emission.

Usage:
    from scripts.pipeline.utils.structured_log import get_logger
    logger = get_logger(__name__)
    logger.info("skill.start", extra={"skill_id": "S-21", "attempt": 1})
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include any extra fields attached to the record
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that emits JSON-formatted records to stdout.

    Idempotent: calling get_logger() multiple times with the same name returns
    the same logger without adding duplicate handlers.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
