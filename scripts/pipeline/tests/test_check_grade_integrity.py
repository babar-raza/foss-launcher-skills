"""Unit tests for check_grade_integrity.py using temp files."""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from check_grade_integrity import _check_file, main  # noqa: E402


def _tmp_md(content: str) -> Path:
    """Write content to a temp .md file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


CLEAN_FILE = """\
---
title: Valid Page
grade: B
graded_at: "2026-03-31T00:00:00Z"
graded_model_sha: abc123
graded_evaluators: full
---
Body text.
"""


class TestCleanFiles:
    def test_valid_grade_block_passes(self):
        p = _tmp_md(CLEAN_FILE)
        try:
            assert _check_file(p) == []
        finally:
            p.unlink(missing_ok=True)

    def test_no_grade_block_passes(self):
        p = _tmp_md("---\ntitle: No grades here\n---\nBody.\n")
        try:
            assert _check_file(p) == []
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_passes(self):
        p = _tmp_md("Just plain text, no frontmatter.\n")
        try:
            assert _check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestAnomalies:
    def test_duplicate_graded_evaluators(self):
        p = _tmp_md("""\
        ---
        title: Dup
        grade: A
        graded_at: "2026-01-01"
        graded_evaluators: full
        graded_evaluators: audit
        ---
        Body.
        """)
        try:
            checks = [i["check"] for i in _check_file(p)]
            assert "duplicate_key" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_grade_value(self):
        p = _tmp_md("""\
        ---
        title: Bad Grade
        grade: Z
        graded_at: "2026-01-01"
        graded_evaluators: full
        ---
        Body.
        """)
        try:
            checks = [i["check"] for i in _check_file(p)]
            assert "invalid_grade" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_grade_missing_graded_at(self):
        p = _tmp_md("""\
        ---
        title: Incomplete
        grade: A
        graded_evaluators: full
        ---
        Body.
        """)
        try:
            checks = [i["check"] for i in _check_file(p)]
            assert "incomplete_block" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_non_consecutive_grade_keys(self):
        p = _tmp_md("""\
        ---
        title: Scattered
        grade: A
        description: interloper
        graded_at: "2026-01-01"
        graded_evaluators: full
        ---
        Body.
        """)
        try:
            checks = [i["check"] for i in _check_file(p)]
            assert "non_consecutive" in checks
        finally:
            p.unlink(missing_ok=True)


class TestInlineCommentEdgeCases:
    """Regression tests for the inline-comment false-positive bug.

    A grade line like ``grade: A # written by evaluator`` contains a valid
    grade (A) followed by an inline YAML comment.  Before the fix, the raw
    value ``A # written by evaluator`` was compared against _VALID_GRADES and
    reported as invalid_grade — a false positive.
    """

    def test_grade_with_inline_comment_passes(self):
        p = _tmp_md(
            "---\ntitle: T\ngrade: A # written by evaluator\n"
            "graded_at: \"2026-03-31T00:00:00Z\"\ngraded_evaluators: full\n---\nBody.\n"
        )
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "invalid_grade" not in checks, (
                f"False positive invalid_grade on 'grade: A # comment': {issues}"
            )
        finally:
            p.unlink(missing_ok=True)

    def test_actually_invalid_grade_still_detected(self):
        p = _tmp_md(
            "---\ntitle: T\ngrade: Z # typo\n"
            "graded_at: \"2026-03-31T00:00:00Z\"\ngraded_evaluators: full\n---\nBody.\n"
        )
        try:
            checks = [i["check"] for i in _check_file(p)]
            assert "invalid_grade" in checks
        finally:
            p.unlink(missing_ok=True)


class TestScopeFiltering:
    def test_non_md_files_skipped_silently(self):
        """GH-05: .py, .yaml, .txt files passed via --files are silently ignored."""
        assert main(["--files", __file__]) == 0  # __file__ is a .py file

    def test_mixed_md_and_non_md_only_md_checked(self, tmp_path):
        bad_md = tmp_path / "bad.md"
        bad_md.write_text(
            "---\ntitle: Dup\ngrade: A\ngraded_at: \"2026-01-01\"\n"
            "graded_evaluators: full\ngraded_evaluators: audit\n---\nBody.\n",
            encoding="utf-8",
        )
        yaml_file = tmp_path / "ignored.yaml"
        yaml_file.write_text("key: value\n", encoding="utf-8")
        # Only bad.md is checked; ignored.yaml is skipped → exit 1 from bad.md
        assert main(["--files", str(bad_md), str(yaml_file)]) == 1


class TestCLI:
    def test_clean_file_exits_0(self):
        p = _tmp_md(CLEAN_FILE)
        try:
            assert main(["--files", str(p)]) == 0
        finally:
            p.unlink(missing_ok=True)

    def test_anomaly_exits_1(self):
        p = _tmp_md(CLEAN_FILE.replace("grade: B", "grade: Z"))
        try:
            assert main(["--files", str(p)]) == 1
        finally:
            p.unlink(missing_ok=True)

    def test_json_output(self, capsys):
        p = _tmp_md(CLEAN_FILE)
        try:
            main(["--files", str(p), "--json"])
            data = json.loads(capsys.readouterr().out)
            assert "files_checked" in data
            assert "anomaly_count" in data
            assert isinstance(data["issues"], list)
        finally:
            p.unlink(missing_ok=True)
