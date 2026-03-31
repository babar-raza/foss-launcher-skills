"""Unit tests for check_grade_integrity.py."""

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


def _tmp_file(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)


VALID_BLOCK = textwrap.dedent("""\
    ---
    title: Test Page
    grade: A
    graded_at: "2026-03-31T00:00:00Z"
    graded_model_sha: abc123
    graded_evaluators: full
    ---
    Body text here.
""")


class TestCheckFile:
    def test_valid_complete_block_no_issues(self):
        p = _tmp_file(VALID_BLOCK)
        try:
            issues = _check_file(p)
            assert issues == [], f"Expected 0 issues, got: {issues}"
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_grade_value(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: Z
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "invalid_grade" in checks, f"Expected invalid_grade, got: {checks}"
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_grade_value_not_first_key(self):
        """grade: is not the first key in grade_positions — tests correct index lookup."""
        content = textwrap.dedent("""\
            ---
            title: Test
            graded_at: "2026-03-31T00:00:00Z"
            grade: X
            graded_model_sha: abc123
            graded_evaluators: full
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "invalid_grade" in checks, f"Expected invalid_grade, got: {checks}"
        finally:
            p.unlink(missing_ok=True)

    def test_duplicate_graded_evaluators(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: A
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            graded_evaluators: audit
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "duplicate_key" in checks, f"Expected duplicate_key, got: {checks}"
        finally:
            p.unlink(missing_ok=True)

    def test_non_consecutive_grade_keys(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: A
            description: Something in between
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "non_consecutive" in checks, f"Expected non_consecutive, got: {checks}"
        finally:
            p.unlink(missing_ok=True)

    def test_incomplete_block_missing_graded_at(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: A
            graded_model_sha: abc123
            graded_evaluators: full
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "incomplete_block" in checks, f"Expected incomplete_block, got: {checks}"
        finally:
            p.unlink(missing_ok=True)

    def test_incomplete_block_missing_graded_evaluators(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: A
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "incomplete_block" in checks, f"Expected incomplete_block, got: {checks}"
        finally:
            p.unlink(missing_ok=True)

    def test_no_grade_keys_no_issues(self):
        content = textwrap.dedent("""\
            ---
            title: Ungraded Page
            description: A page without any grade metadata.
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            assert issues == [], f"Expected 0 issues on ungraded file, got: {issues}"
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_no_issues(self):
        p = _tmp_file("Just a body, no frontmatter.\n")
        try:
            issues = _check_file(p)
            assert issues == []
        finally:
            p.unlink(missing_ok=True)

    def test_valid_grade_b(self):
        content = VALID_BLOCK.replace("grade: A", "grade: B")
        p = _tmp_file(content)
        try:
            issues = _check_file(p)
            checks = [i["check"] for i in issues]
            assert "invalid_grade" not in checks
        finally:
            p.unlink(missing_ok=True)


class TestMainCLI:
    def test_clean_file_exits_0(self, capsys):
        p = _tmp_file(VALID_BLOCK)
        try:
            rc = main(["--scope", "modified", str(p)])
            assert rc == 0
        finally:
            p.unlink(missing_ok=True)

    def test_malformed_file_exits_1(self, capsys):
        content = VALID_BLOCK.replace("grade: A", "grade: Z")
        p = _tmp_file(content)
        try:
            rc = main(["--scope", "modified", str(p)])
            assert rc == 1
        finally:
            p.unlink(missing_ok=True)

    def test_translated_file_skipped(self, capsys):
        """A .fa.md file with invalid grade should be skipped (0 issues)."""
        content = VALID_BLOCK.replace("grade: A", "grade: Z")
        f = tempfile.NamedTemporaryFile(
            suffix=".fa.md", mode="w", encoding="utf-8", delete=False
        )
        f.write(content)
        f.close()
        p = Path(f.name)
        try:
            rc = main(["--scope", "modified", str(p)])
            # Translation file excluded → exits 0
            assert rc == 0
        finally:
            p.unlink(missing_ok=True)

    def test_json_output_shape(self, capsys):
        p = _tmp_file(VALID_BLOCK)
        try:
            rc = main(["--scope", "modified", "--json", str(p)])
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert "issues" in data
            assert "files_checked" in data
            assert isinstance(data["issues"], list)
        finally:
            p.unlink(missing_ok=True)

    def test_modified_scope_excludes_unrelated_file(self, capsys):
        """Only the file passed as argument is checked, not the whole tree."""
        good = _tmp_file(VALID_BLOCK)
        bad_content = VALID_BLOCK.replace("grade: A", "grade: Z")
        bad = _tmp_file(bad_content)
        try:
            # Pass only the good file — bad file should not be checked
            rc = main(["--scope", "modified", str(good)])
            assert rc == 0
        finally:
            good.unlink(missing_ok=True)
            bad.unlink(missing_ok=True)
