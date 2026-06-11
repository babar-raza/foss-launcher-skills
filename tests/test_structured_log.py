"""Tests for scripts/pipeline/utils/structured_log.py.

Verifies that the JSON formatter produces valid, well-structured output
and that get_logger() is idempotent.
"""
from __future__ import annotations

import json
import logging
import io
import sys

import pytest

from scripts.pipeline.utils.structured_log import get_logger, _JsonFormatter


class TestJsonFormatter:
    """Tests for _JsonFormatter."""

    def _make_record(self, msg: str, level: int = logging.INFO, **kwargs) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        formatter = _JsonFormatter()
        record = self._make_record("hello")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_level_field_present(self):
        formatter = _JsonFormatter()
        record = self._make_record("test message", level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"

    def test_message_field_present(self):
        formatter = _JsonFormatter()
        record = self._make_record("my message")
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "my message"

    def test_logger_name_present(self):
        formatter = _JsonFormatter()
        record = self._make_record("msg")
        parsed = json.loads(formatter.format(record))
        assert parsed["logger"] == "test.logger"

    def test_extra_fields_included(self):
        formatter = _JsonFormatter()
        record = self._make_record("msg", skill_id="S-21")
        parsed = json.loads(formatter.format(record))
        assert parsed["skill_id"] == "S-21"


class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_logger_instance(self):
        logger = get_logger("test.get_logger.basic")
        assert isinstance(logger, logging.Logger)

    def test_idempotent_no_duplicate_handlers(self):
        name = "test.get_logger.idempotent"
        logger1 = get_logger(name)
        handler_count_after_first = len(logger1.handlers)
        logger2 = get_logger(name)
        assert logger1 is logger2
        assert len(logger2.handlers) == handler_count_after_first

    def test_logger_name_matches(self):
        logger = get_logger("test.get_logger.name")
        assert logger.name == "test.get_logger.name"

    def test_emit_produces_json_to_stdout(self, capsys):
        logger = get_logger("test.get_logger.emit")
        logger.info("structured test message")
        captured = capsys.readouterr()
        # At least one line of stdout should be valid JSON
        lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert parsed["message"] == "structured test message"
        assert parsed["level"] == "INFO"
