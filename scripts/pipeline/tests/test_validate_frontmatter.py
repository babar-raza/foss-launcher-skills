"""Unit tests for validate_frontmatter.py using temp files."""

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

from validate_frontmatter import check_file, main  # noqa: E402


def _tmp_md(content: str) -> Path:
    """Write content to a temp .md file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


CLEAN_FILE = """\
---
title: Valid Page
type: docs
weight: 10
---
Body text.
"""


class TestCleanFiles:
    def test_valid_frontmatter_passes(self):
        p = _tmp_md(CLEAN_FILE)
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_passes(self):
        p = _tmp_md("Just plain text, no frontmatter.\n")
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)

    def test_empty_file_passes(self):
        p = _tmp_md("")
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestDuplicateKeys:
    def test_duplicate_top_level_key_detected(self):
        p = _tmp_md("""\
        ---
        title: First
        title: Second
        type: docs
        ---
        Body.
        """)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "duplicate_key" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_duplicate_grade_key_detected(self):
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
            errors = check_file(p)
            keys = [e.check for e in errors]
            assert "duplicate_key" in keys
            assert any("graded_evaluators" in e.detail for e in errors)
        finally:
            p.unlink(missing_ok=True)

    def test_unique_keys_no_error(self):
        p = _tmp_md("""\
        ---
        title: Clean
        grade: A
        graded_at: "2026-01-01"
        graded_evaluators: full
        ---
        Body.
        """)
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestDoubleFrontmatter:
    def test_double_frontmatter_detected(self):
        """Two separate --- blocks at the top is a structural error."""
        content = (
            "---\n"
            "provenance:\n"
            "  translation_origin: translator\n"
            "---\n"
            "\n"
            "---\n"
            "title: Real Title\n"
            "type: docs\n"
            "---\n"
            "Body.\n"
        )
        p = _tmp_md(content)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "double_frontmatter" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_double_frontmatter_reports_second_block_key(self):
        """Error message hints at the first key in the second block."""
        content = (
            "---\n"
            "provenance:\n"
            "  translation_origin: translator\n"
            "---\n"
            "\n"
            "---\n"
            "layout: family\n"
            "title: Something\n"
            "---\n"
            "Body.\n"
        )
        p = _tmp_md(content)
        try:
            errors = check_file(p)
            double = [e for e in errors if e.check == "double_frontmatter"]
            assert double, "Expected double_frontmatter error"
            assert "layout" in double[0].detail
        finally:
            p.unlink(missing_ok=True)

    def test_single_frontmatter_no_error(self):
        """File with one --- block and body containing dashes does not trigger."""
        content = (
            "---\n"
            "title: Dashes in body\n"
            "---\n"
            "Some text with --- in a line.\n"
            "More text.\n"
        )
        p = _tmp_md(content)
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestCLI:
    def test_clean_file_exits_0(self):
        p = _tmp_md(CLEAN_FILE)
        try:
            assert main([str(p)]) == 0
        finally:
            p.unlink(missing_ok=True)

    def test_duplicate_key_exits_1(self):
        p = _tmp_md("""\
        ---
        title: X
        title: Y
        ---
        Body.
        """)
        try:
            assert main([str(p)]) == 1
        finally:
            p.unlink(missing_ok=True)

    def test_double_frontmatter_exits_1(self):
        content = (
            "---\n"
            "provenance:\n"
            "  translation_origin: translator\n"
            "---\n"
            "\n"
            "---\n"
            "title: Real\n"
            "---\n"
            "Body.\n"
        )
        p = _tmp_md(content)
        try:
            assert main([str(p)]) == 1
        finally:
            p.unlink(missing_ok=True)

    def test_json_output(self, capsys):
        p = _tmp_md("""\
        ---
        title: X
        title: Y
        ---
        Body.
        """)
        try:
            main([str(p), "--json"])
            data = json.loads(capsys.readouterr().out)
            assert isinstance(data, list)
            assert len(data) >= 1
            assert data[0]["check"] == "duplicate_key"
        finally:
            p.unlink(missing_ok=True)
