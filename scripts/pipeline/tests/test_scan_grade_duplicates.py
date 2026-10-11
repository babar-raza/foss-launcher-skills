"""Unit tests for scan_grade_duplicates.py."""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

_CI_ROOT = Path(__file__).resolve().parent.parent.parent / "ci" / "checks"
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

from scan_grade_duplicates import scan_file, main  # noqa: E402


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


class TestScanFile:
    def test_clean_file_no_findings(self):
        p = _tmp_file(VALID_BLOCK)
        try:
            findings = scan_file(p)
            assert findings == [], f"Expected 0 findings, got: {findings}"
        finally:
            p.unlink(missing_ok=True)

    def test_duplicate_grade_key(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: A
            grade: B
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            findings = scan_file(p)
            errors = [f for f in findings if f["severity"] == "ERROR"]
            assert len(errors) >= 1
            assert any("grade" in f["message"] and "2 occurrences" in f["message"] for f in errors)
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
            findings = scan_file(p)
            errors = [f for f in findings if f["severity"] == "ERROR"]
            assert len(errors) >= 1
            assert any("graded_evaluators" in f["message"] for f in errors)
        finally:
            p.unlink(missing_ok=True)

    def test_orphaned_key_non_consecutive(self):
        """graded_evaluators separated from main block is a WARN (orphan)."""
        content = textwrap.dedent("""\
            ---
            title: Test
            grade: A
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            description: Something in between
            graded_evaluators: orphan
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            findings = scan_file(p)
            # Duplicate key is an ERROR; orphan on second block is WARN
            severities = {f["severity"] for f in findings}
            assert len(findings) >= 1
            # At minimum the duplicate should be flagged as ERROR
            assert "ERROR" in severities
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_grade_value(self):
        content = VALID_BLOCK.replace("grade: A", "grade: X")
        p = _tmp_file(content)
        try:
            findings = scan_file(p)
            errors = [f for f in findings if f["severity"] == "ERROR"]
            assert len(errors) >= 1
            assert any("Invalid grade" in f["message"] for f in errors)
        finally:
            p.unlink(missing_ok=True)

    def test_graded_at_without_grade(self):
        content = textwrap.dedent("""\
            ---
            title: Test
            graded_at: "2026-03-31T00:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            findings = scan_file(p)
            warns = [f for f in findings if f["severity"] == "WARN"]
            assert len(warns) >= 1
            assert any("graded_at" in f["message"] for f in warns)
        finally:
            p.unlink(missing_ok=True)

    def test_no_grade_keys_no_findings(self):
        content = textwrap.dedent("""\
            ---
            title: Ungraded
            description: No grade metadata here.
            ---
            Body.
        """)
        p = _tmp_file(content)
        try:
            findings = scan_file(p)
            assert findings == []
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_no_findings(self):
        p = _tmp_file("Just body text.\n")
        try:
            findings = scan_file(p)
            assert findings == []
        finally:
            p.unlink(missing_ok=True)


class TestMainCLI:
    def test_exit_code_0_on_clean_directory(self, tmp_path, monkeypatch):
        (tmp_path / "clean.md").write_text(VALID_BLOCK, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["scan_grade_duplicates", str(tmp_path)])
        rc = main()
        assert rc == 0

    def test_exit_code_1_on_duplicate(self, tmp_path, monkeypatch, capsys):
        content = VALID_BLOCK.replace(
            "graded_evaluators: full",
            "graded_evaluators: full\ngraded_evaluators: audit",
        )
        (tmp_path / "bad.md").write_text(content, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["scan_grade_duplicates", str(tmp_path)])
        rc = main()
        assert rc == 1

    def test_mixed_files_only_bad_reported(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "good.md").write_text(VALID_BLOCK, encoding="utf-8")
        bad = VALID_BLOCK.replace("grade: A", "grade: Z")
        (tmp_path / "bad.md").write_text(bad, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["scan_grade_duplicates", str(tmp_path)])
        rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "bad.md" in captured.out
        assert "good.md" not in captured.out
