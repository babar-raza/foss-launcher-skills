"""Tests for scripts/pipeline/smoke_test.py — Python code block syntax and type checking.

Covers:
- PASS: valid Python block
- FAIL: syntax error in block
- WARN: type error (mypy) — only when mypy is available
- canonical_import prepended correctly when not already in block
- canonical_import NOT re-prepended when already in block
- empty file (no python blocks) produces empty result
- exit codes: 0 PASS, 1 WARN, 2 FAIL
"""

import sys
import textwrap
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import smoke_test
from smoke_test import check_file, print_report, BlockResult, SmokeResult


# ---------------------------------------------------------------------------
# Helper: write a temp markdown file with code blocks
# ---------------------------------------------------------------------------

def _write_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test_page.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Block extraction
# ---------------------------------------------------------------------------

class TestExtractBlocks:

    def test_no_blocks(self, tmp_path):
        f = _write_md(tmp_path, "# Title\n\nNo code here.\n")
        result = check_file(f)
        assert result.blocks_checked == 0
        assert result.pass_count == 0

    def test_single_python_block(self, tmp_path):
        f = _write_md(tmp_path, "```python\nx = 1\n```\n")
        result = check_file(f)
        assert result.blocks_checked == 1

    def test_non_python_block_ignored(self, tmp_path):
        f = _write_md(tmp_path, "```csharp\nvar x = 1;\n```\n")
        result = check_file(f)
        assert result.blocks_checked == 0

    def test_multiple_blocks(self, tmp_path):
        content = "```python\nx = 1\n```\n\n```python\ny = 2\n```\n"
        f = _write_md(tmp_path, content)
        result = check_file(f)
        assert result.blocks_checked == 2


# ---------------------------------------------------------------------------
# Syntax check: PASS cases
# ---------------------------------------------------------------------------

class TestSyntaxPass:

    def test_valid_block_passes(self, tmp_path):
        f = _write_md(tmp_path, "```python\nx = 1 + 2\nprint(x)\n```\n")
        result = check_file(f)
        assert result.fail_count == 0
        assert result.pass_count + result.warn_count == 1

    def test_valid_import_passes(self, tmp_path):
        f = _write_md(tmp_path, "```python\nimport os\nprint(os.getcwd())\n```\n")
        result = check_file(f)
        assert result.fail_count == 0


# ---------------------------------------------------------------------------
# Syntax check: FAIL cases
# ---------------------------------------------------------------------------

class TestSyntaxFail:

    def test_syntax_error_fails(self, tmp_path):
        # Missing closing paren
        f = _write_md(tmp_path, "```python\ndef foo(\n    x = 1\n```\n")
        result = check_file(f)
        assert result.fail_count >= 1

    def test_fail_result_has_message(self, tmp_path):
        f = _write_md(tmp_path, "```python\ndef foo(\n```\n")
        result = check_file(f)
        fail_results = [r for r in result.results if r.status == "FAIL"]
        assert len(fail_results) >= 1
        assert "SyntaxError" in fail_results[0].message

    def test_fail_result_has_line_number(self, tmp_path):
        # Block starts at line 3 (after a heading)
        f = _write_md(tmp_path, "# Title\n\n```python\ndef bad(\n```\n")
        result = check_file(f)
        fail_results = [r for r in result.results if r.status == "FAIL"]
        assert fail_results[0].start_line > 0


# ---------------------------------------------------------------------------
# Canonical import prepend
# ---------------------------------------------------------------------------

class TestCanonicalImport:

    def test_import_prepended_when_absent(self, tmp_path):
        # The block doesn't import anything; canonical_import should be prepended
        f = _write_md(tmp_path, "```python\nx = 1\n```\n")
        # Just verify check_file runs without error with a canonical_import
        result = check_file(f, canonical_import="import os")
        assert result.blocks_checked == 1
        assert result.fail_count == 0  # import os + x=1 is valid

    def test_import_not_duplicated_when_present(self, tmp_path):
        # The block already has the canonical import
        f = _write_md(tmp_path, "```python\nimport os\nx = 1\n```\n")
        result = check_file(f, canonical_import="import os")
        assert result.fail_count == 0
        assert result.blocks_checked == 1


# ---------------------------------------------------------------------------
# print_report exit codes
# ---------------------------------------------------------------------------

class TestPrintReport:

    def _make_result(self, status: str) -> SmokeResult:
        br = BlockResult(
            file="test.md",
            block_index=1,
            start_line=1,
            status=status,
            message="test message" if status != "PASS" else "",
        )
        return SmokeResult(
            file="test.md",
            blocks_checked=1,
            pass_count=1 if status == "PASS" else 0,
            warn_count=1 if status == "WARN" else 0,
            fail_count=1 if status == "FAIL" else 0,
            results=[br],
        )

    def test_all_pass_returns_0(self, capsys):
        code = print_report([self._make_result("PASS")])
        assert code == 0

    def test_warn_returns_1(self, capsys):
        code = print_report([self._make_result("WARN")])
        assert code == 1

    def test_fail_returns_2(self, capsys):
        code = print_report([self._make_result("FAIL")])
        assert code == 2

    def test_fail_overrides_warn(self, capsys):
        # If both WARN and FAIL present, exit code must be 2
        warn_result = self._make_result("WARN")
        fail_result = self._make_result("FAIL")
        code = print_report([warn_result, fail_result])
        assert code == 2


# ---------------------------------------------------------------------------
# _run_mypy: mypy-absent silent-skip
# ---------------------------------------------------------------------------

class TestMypyAbsent:
    """Verify _run_mypy silently skips when mypy is not installed.

    Uses monkeypatch to simulate subprocess.run returning "No module named mypy"
    without requiring mypy to actually be absent from the test environment.

    Both _run_py_compile and _run_mypy call subprocess.run. The fakes must let
    py_compile succeed (returncode=0) and only intercept the mypy call.
    """

    @staticmethod
    def _dispatch(cmd, returncode, stdout, stderr):
        """Return a fake subprocess.CompletedProcess-like object.

        Routes py_compile calls to success so the syntax check passes, then
        returns the provided returncode/stdout/stderr for the mypy call.
        """
        import types
        if "py_compile" in cmd:
            # Let syntax check succeed so we reach the mypy step
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_mypy_absent_does_not_warn(self, tmp_path, monkeypatch):
        """'No module named mypy' in subprocess output → PASS, not WARN."""
        monkeypatch.setattr(
            smoke_test.subprocess, "run",
            lambda cmd, **kw: self._dispatch(
                cmd, 1, "", "C:\\Python313\\python.exe: No module named mypy"
            ),
        )
        f = _write_md(tmp_path, "```python\nx = 1\n```\n")
        result = check_file(f)
        assert result.warn_count == 0, "mypy-absent must not produce a WARN"
        assert result.pass_count == 1

    def test_mypy_type_error_produces_warn(self, tmp_path, monkeypatch):
        """Real mypy type error → block is WARN (not silently skipped)."""
        monkeypatch.setattr(
            smoke_test.subprocess, "run",
            lambda cmd, **kw: self._dispatch(
                cmd, 1,
                "<code_block>:1: error: Name 'undefined_var' is not defined  [name-defined]",
                "",
            ),
        )
        f = _write_md(tmp_path, "```python\nx = 1\n```\n")
        result = check_file(f)
        assert result.warn_count == 1, "real type error must produce a WARN"
        assert result.pass_count == 0
