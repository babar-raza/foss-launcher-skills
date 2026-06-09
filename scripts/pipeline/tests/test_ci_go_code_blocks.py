"""Tests for scripts/ci/checks/check_go_code_blocks.py — Go code block CI gate.

Tests the Python wrapping/extraction logic only. Does NOT require Go on PATH.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the ci/checks module importable
_CI_CHECKS = Path(__file__).resolve().parents[2] / "ci" / "checks"
sys.path.insert(0, str(_CI_CHECKS))

from check_go_code_blocks import (
    _GO_BLOCK_RE,
    _infer_imports,
    _needs_package_wrapper,
    _wrap_fragment,
)


class TestGoBlockExtraction:
    """Test _GO_BLOCK_RE regex extraction from markdown."""

    def test_extracts_go_blocks(self):
        md = "# Title\n\n```go\nfmt.Println(\"hi\")\n```\n\nSome text.\n"
        blocks = _GO_BLOCK_RE.findall(md)
        assert len(blocks) == 1
        assert 'fmt.Println("hi")' in blocks[0]

    def test_ignores_non_go_blocks(self):
        md = "```python\nprint('hi')\n```\n\n```bash\necho hi\n```\n"
        blocks = _GO_BLOCK_RE.findall(md)
        assert blocks == []

    def test_extracts_multiple_blocks(self):
        md = "```go\nblock1()\n```\n\ntext\n\n```go\nblock2()\n```\n"
        blocks = _GO_BLOCK_RE.findall(md)
        assert len(blocks) == 2


class TestWrapFragment:
    """Test _wrap_fragment and _needs_package_wrapper logic."""

    def test_wrap_adds_package_main(self):
        code = 'fmt.Println("hello")'
        wrapped = _wrap_fragment(code)
        assert "package main" in wrapped
        assert "func main() {" in wrapped
        assert 'fmt.Println("hello")' in wrapped

    def test_full_program_not_wrapped(self):
        code = 'package main\n\nfunc main() {\n\tfmt.Println("hi")\n}'
        assert not _needs_package_wrapper(code)

    def test_standalone_code_needs_wrapper(self):
        code = 'doc, _ := pdf.Open("test.pdf")\nfmt.Println(doc.PageCount())'
        assert _needs_package_wrapper(code)


class TestInferImports:
    """Test _infer_imports heuristic."""

    def test_infer_pdf_import(self):
        code = 'doc, _ := pdf.Open("test.pdf")'
        imports = _infer_imports(code)
        assert any("pdf" in imp for imp in imports)

    def test_infer_fmt_import(self):
        code = 'fmt.Println("hello")'
        imports = _infer_imports(code)
        assert any('"fmt"' in imp for imp in imports)

    def test_infer_os_import(self):
        code = 'f, _ := os.Create("out.pdf")'
        imports = _infer_imports(code)
        assert any('"os"' in imp for imp in imports)

    def test_no_imports_for_plain_code(self):
        code = 'x := 42\ny := x + 1'
        imports = _infer_imports(code)
        assert imports == []
