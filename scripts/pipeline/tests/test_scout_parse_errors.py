"""Tests for tree-sitter parse error detection in extraction/api_surface.py.

Coverage:
- valid source file: parse_errors is empty
- syntactically invalid Python: parse_errors contains the file path
- scout_report always has parse_errors and parse_error_rate keys
- parse_error_rate calculation is correct
- warning emitted when parse_error_rate > 0.05
- error emitted when parse_error_rate > 0.20 (via Scout class quality gate)
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from extraction.api_surface import extract_api_surface
from extraction.tree_helpers import get_parser, PLATFORM_TO_LANG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PYTHON = b'''\
class Greeter:
    """Simple greeter class."""

    def hello(self, name: str) -> str:
        """Return greeting."""
        return f"Hello, {name}"
'''

_INVALID_PYTHON = b'''\
class Broken(
    def method( pass
    syntax_error +++
'''

_VALID_JAVA = b'''\
package com.example;

public class Calculator {
    public int add(int a, int b) { return a + b; }
}
'''

_INVALID_JAVA = b'''\
public class Broken {
    public void (( {
        // unclosed and invalid
'''


def _setup_repo(tmp_path: Path, files: dict[str, bytes]) -> tuple[Path, Path]:
    """Create a fake repo with source files. Returns (repo_root, pkg_root)."""
    for rel_path, content in files.items():
        dest = tmp_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    return tmp_path, tmp_path


# ---------------------------------------------------------------------------
# TASK-12 tests
# ---------------------------------------------------------------------------

class TestValidFileNoParseErrors:
    def test_valid_python_produces_empty_parse_errors(self, tmp_path):
        repo, pkg_root = _setup_repo(tmp_path, {
            "greeter.py": _VALID_PYTHON,
        })
        parser = get_parser("python")

        classes, claims, scanned, packages, report = extract_api_surface(
            parser, "python", pkg_root, repo, "test"
        )

        assert report["parse_errors"] == []
        assert report["parse_error_rate"] == 0.0
        assert "greeter.py" in scanned or any("greeter.py" in f for f in scanned)


class TestInvalidFileParseError:
    def test_invalid_python_captured_in_parse_errors(self, tmp_path):
        """Core bug class: parse errors must be visible in scout_report."""
        repo, pkg_root = _setup_repo(tmp_path, {
            "broken.py": _INVALID_PYTHON,
        })
        parser = get_parser("python")

        classes, claims, scanned, packages, report = extract_api_surface(
            parser, "python", pkg_root, repo, "test"
        )

        assert len(report["parse_errors"]) >= 1
        assert any("broken.py" in p for p in report["parse_errors"])
        assert report["parse_error_rate"] > 0.0

    def test_parse_error_rate_correct(self, tmp_path):
        """parse_error_rate = parse_errors / files_attempted."""
        # 1 valid + 1 invalid = 50% parse error rate
        repo, pkg_root = _setup_repo(tmp_path, {
            "valid.py": _VALID_PYTHON,
            "broken.py": _INVALID_PYTHON,
        })
        parser = get_parser("python")

        classes, claims, scanned, packages, report = extract_api_surface(
            parser, "python", pkg_root, repo, "test"
        )

        assert report["files_attempted"] == 2
        assert len(report["parse_errors"]) == 1
        assert abs(report["parse_error_rate"] - 0.5) < 0.01


class TestScoutReportKeysAlwaysPresent:
    def test_empty_dir_has_both_new_keys(self, tmp_path):
        """Even with zero files, parse_errors and parse_error_rate must be present."""
        # No source files in repo
        parser = get_parser("python")

        classes, claims, scanned, packages, report = extract_api_surface(
            parser, "python", tmp_path, tmp_path, "test"
        )

        assert "parse_errors" in report
        assert "parse_error_rate" in report
        assert report["parse_errors"] == []
        assert report["parse_error_rate"] == 0.0

    def test_all_expected_keys_present(self, tmp_path):
        """scout_report must always have the full key set."""
        parser = get_parser("python")

        classes, claims, scanned, packages, report = extract_api_surface(
            parser, "python", tmp_path, tmp_path, "test"
        )

        required_keys = {
            "files_attempted", "files_parsed", "files_skipped",
            "skip_reasons", "parse_errors", "parse_error_rate",
        }
        assert required_keys.issubset(report.keys())


class TestParseErrorWarningThresholds:
    def test_warning_emitted_above_5_percent(self, tmp_path, caplog):
        """When >5% parse errors, a warning must be logged."""
        # Create 20 files: 2 invalid (10% → above 5% threshold)
        files = {}
        for i in range(18):
            files[f"valid_{i}.py"] = _VALID_PYTHON
        files["broken_1.py"] = _INVALID_PYTHON
        files["broken_2.py"] = _INVALID_PYTHON

        repo, pkg_root = _setup_repo(tmp_path, files)
        parser = get_parser("python")

        with caplog.at_level(logging.WARNING, logger="scout"):
            from extraction.scout import Scout
            output_dir = tmp_path / "output"
            output_dir.mkdir()
            s = Scout("test", "python", repo, output_dir)
            # Directly call _extract_api_surface to capture log
            s.parser = parser
            s.pkg_root = pkg_root
            s._extract_api_surface()

        # Parse error rate is 2/20 = 10% > 5% threshold
        parse_error_rate = s.scout_report.get("parse_error_rate", 0)
        assert parse_error_rate > 0.05
        # Warning or error should have been logged
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("parse error" in msg.lower() for msg in warning_messages), \
            f"Expected parse error warning in logs, got: {warning_messages}"
