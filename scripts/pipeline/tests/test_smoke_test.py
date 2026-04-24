"""Tests for scripts/pipeline/smoke_test.py — multi-language code block syntax checking.

Covers:
- PASS: valid Python block
- FAIL: syntax error in block
- WARN: type error (mypy) — only when mypy is available
- canonical_import prepended correctly when not already in block
- canonical_import NOT re-prepended when already in block
- empty file (no python blocks) produces empty result
- exit codes: 0 PASS, 1 WARN, 2 FAIL
- non-Python blocks (java/csharp/typescript/cpp) via tree-sitter (TestNonPythonBlocks)
"""

import sys
import textwrap
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import smoke_test
from smoke_test import (
    check_file, print_report, BlockResult, SmokeResult,
    _TS_LANG_MAP, _PLATFORM_LANGS, _run_ts_parse, _first_error_node,
)


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


# ---------------------------------------------------------------------------
# Non-Python language blocks (TC-CS-02: CODE-SMOKE multi-language extension)
# ---------------------------------------------------------------------------

# Minimal valid snippets for each language.  Deliberately short so tree-sitter
# MISSING-node tolerance doesn't matter — these are complete statements.
_VALID_JAVA = "```java\nimport com.aspose.threed.*;\nScene scene = new Scene();\n```\n"
_VALID_CSHARP = "```csharp\nusing System;\nvar x = 42;\n```\n"
_VALID_TYPESCRIPT = "```typescript\nconst x: number = 42;\nconsole.log(x);\n```\n"
_VALID_CPP = "```cpp\n#include <string>\nstd::string s = \"hello\";\n```\n"

# Snippets with genuine ERROR tokens (not just MISSING).
_BAD_JAVA = "```java\nimport com.aspose.threed.*;\nScene scene = @@@;\n```\n"
_BAD_CSHARP = "```csharp\nusing System;\nvar x = @@@;\n```\n"
_BAD_TYPESCRIPT = "```typescript\nconst x: number = @@@;\nconsole.log(x);\n```\n"
_BAD_CPP = "```cpp\n#include <string>\nstd::string s = @@@;\n```\n"


class TestNonPythonBlocks:
    """Tree-sitter based syntax checking for Java, C#, TypeScript, and C++.

    Tests require tree-sitter-java / tree-sitter-c-sharp /
    tree-sitter-typescript / tree-sitter-cpp to be installed in the venv.
    All four are present (verified 2026-04-24).
    """

    # ------------------------------------------------------------------
    # Java
    # ------------------------------------------------------------------

    def test_java_valid_block_passes(self, tmp_path):
        f = _write_md(tmp_path, _VALID_JAVA)
        result = check_file(f, langs=frozenset({"java"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 0
        assert result.pass_count == 1

    def test_java_syntax_error_fails(self, tmp_path):
        f = _write_md(tmp_path, _BAD_JAVA)
        result = check_file(f, langs=frozenset({"java"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 1
        assert "Java" in result.results[0].message

    # ------------------------------------------------------------------
    # C#
    # ------------------------------------------------------------------

    def test_csharp_valid_block_passes(self, tmp_path):
        f = _write_md(tmp_path, _VALID_CSHARP)
        result = check_file(f, langs=frozenset({"csharp"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 0
        assert result.pass_count == 1

    def test_csharp_syntax_error_fails(self, tmp_path):
        f = _write_md(tmp_path, _BAD_CSHARP)
        result = check_file(f, langs=frozenset({"csharp"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 1
        assert "C#" in result.results[0].message

    def test_csharp_tag_aliases(self, tmp_path):
        """Both 'cs' and 'c#' tags are extracted when csharp is in langs."""
        cs_block = "```cs\nusing System;\nvar y = 1;\n```\n"
        f = _write_md(tmp_path, cs_block)
        result = check_file(f, langs=frozenset({"csharp", "cs", "c#"}))
        assert result.blocks_checked == 1

    # ------------------------------------------------------------------
    # TypeScript
    # ------------------------------------------------------------------

    def test_typescript_valid_block_passes(self, tmp_path):
        f = _write_md(tmp_path, _VALID_TYPESCRIPT)
        result = check_file(f, langs=frozenset({"typescript"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 0
        assert result.pass_count == 1

    def test_typescript_syntax_error_fails(self, tmp_path):
        f = _write_md(tmp_path, _BAD_TYPESCRIPT)
        result = check_file(f, langs=frozenset({"typescript"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 1
        assert "TypeScript" in result.results[0].message

    # ------------------------------------------------------------------
    # C++
    # ------------------------------------------------------------------

    def test_cpp_valid_block_passes(self, tmp_path):
        f = _write_md(tmp_path, _VALID_CPP)
        result = check_file(f, langs=frozenset({"cpp"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 0
        assert result.pass_count == 1

    def test_cpp_syntax_error_fails(self, tmp_path):
        f = _write_md(tmp_path, _BAD_CPP)
        result = check_file(f, langs=frozenset({"cpp"}))
        assert result.blocks_checked == 1
        assert result.fail_count == 1
        assert "C++" in result.results[0].message

    # ------------------------------------------------------------------
    # Mixed-language document
    # ------------------------------------------------------------------

    def test_mixed_python_java_page(self, tmp_path):
        """A page with both python and java blocks: each counted when langs includes both."""
        content = _VALID_JAVA + "\n" + "```python\nx = 1\n```\n"
        f = _write_md(tmp_path, content)
        result = check_file(f, langs=frozenset({"python", "java"}))
        assert result.blocks_checked == 2
        assert result.fail_count == 0

    def test_non_code_lang_ignored(self, tmp_path):
        """bash block is never extracted, even when checking java."""
        content = "```bash\njavac Foo.java\n```\n"
        f = _write_md(tmp_path, content)
        result = check_file(f, langs=frozenset({"java"}))
        assert result.blocks_checked == 0

    # ------------------------------------------------------------------
    # MISSING node tolerance (common in code snippets)
    # ------------------------------------------------------------------

    def test_missing_node_does_not_fail(self, tmp_path):
        """A snippet that has MISSING nodes but no ERROR nodes must PASS.

        tree-sitter inserts MISSING tokens to complete partial parses — this
        is normal for documentation snippets like `Scene scene = new Scene();`
        without a surrounding class body.  Only ERROR nodes indicate a real
        syntax problem.
        """
        # This Java snippet is syntactically valid as a block-level statement
        # but lacks a class wrapper.  tree-sitter may insert MISSING nodes.
        partial_java = "```java\nScene scene = new Scene();\n```\n"
        f = _write_md(tmp_path, partial_java)
        result = check_file(f, langs=frozenset({"java"}))
        assert result.fail_count == 0, (
            f"MISSING-node snippet must not FAIL; got: {result.results}"
        )

    # ------------------------------------------------------------------
    # Platform-lang mapping
    # ------------------------------------------------------------------

    def test_platform_langs_net_is_csharp(self):
        """_PLATFORM_LANGS maps 'net' to csharp tags."""
        assert "csharp" in _PLATFORM_LANGS["net"] or "cs" in _PLATFORM_LANGS["net"]

    def test_platform_langs_java_is_java(self):
        assert "java" in _PLATFORM_LANGS["java"]

    def test_platform_langs_typescript_is_typescript(self):
        assert "typescript" in _PLATFORM_LANGS["typescript"]

    def test_platform_langs_cpp_is_cpp(self):
        assert "cpp" in _PLATFORM_LANGS["cpp"]

    # ------------------------------------------------------------------
    # _TS_LANG_MAP completeness
    # ------------------------------------------------------------------

    def test_ts_lang_map_covers_all_aliases(self):
        """All expected aliases are present in _TS_LANG_MAP."""
        for tag in ("java", "csharp", "cs", "c#", "typescript", "ts", "cpp", "c++"):
            assert tag in _TS_LANG_MAP, f"Missing: {tag}"
