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
    _has_top_level_main,
    _infer_imports,
    _needs_package_wrapper,
    _resolve_go_module,
    _wrap_fragment,
)

# MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION/C5: _find_module_replace_path
# moved to lib/example_verification/runners/go.py alongside the functions above --
# imported directly (not re-exported by check_go_code_blocks.py, since the pre-C5
# module never exposed it as part of its own public re-export surface either; it's a
# private helper _vet_block calls internally).
_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from example_verification.runners.go import _find_module_replace_path  # noqa: E402


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


class TestCompleteProgramNotDoubleWrapped:
    """HARDEN-GO-VET (cells/go launch, 2026-07-28): a code block that is
    already a complete `func main() { ... }` program (real upstream
    examples/snippets are frequently written this way, not as bare
    fragments) must not be nested inside a SECOND func main -- Go only
    allows anonymous `func() {}` literals inside a function body, so the
    old unconditional wrap produced a real parse error
    ("expected '(', found main") on every such block.
    """

    def test_detects_top_level_main(self):
        assert _has_top_level_main('func main() {\n\tfmt.Println("hi")\n}')

    def test_detects_indented_top_level_main(self):
        # Code blocks extracted from YAML frontmatter (e.g. a products page's
        # single.block[].content) retain their original indentation --
        # the detection must not require column-0 placement.
        assert _has_top_level_main('      func main() {\n      \tfmt.Println("hi")\n      }')

    def test_plain_fragment_has_no_top_level_main(self):
        assert not _has_top_level_main('fmt.Println("hi")')

    def test_bare_func_main_not_double_wrapped(self):
        code = 'func main() {\n\tfmt.Println("hi")\n}'
        wrapped = _wrap_fragment(code)
        assert wrapped.count("func main(") == 1

    def test_func_main_with_leading_import_not_double_wrapped(self):
        code = (
            'import (\n'
            '\t"fmt"\n'
            ')\n\n'
            'func main() {\n'
            '\tfmt.Println("hi")\n'
            '}'
        )
        wrapped = _wrap_fragment(code)
        assert wrapped.count("func main(") == 1

    def test_plain_fragment_still_wrapped_once(self):
        # Regression guard: the ordinary fragment-wrapping path (no
        # pre-existing func main) must be unaffected by this fix.
        code = 'fmt.Println("hi")'
        wrapped = _wrap_fragment(code)
        assert wrapped.count("func main(") == 1


class TestResolveGoModule:
    """HARDEN-GO-VET: module/import resolution must generalize beyond the
    hardcoded pdf/go default to any Go product with scouted knowledge.
    """

    def test_resolves_from_real_model_yaml(self, tmp_path):
        family_dir = tmp_path / "knowledge" / "widgets" / "go" / "scout"
        family_dir.mkdir(parents=True)
        (family_dir / "model.yaml").write_text(
            'family: widgets\n'
            'platform: go\n'
            'package_name: github.com/example/widgets-go/v3\n'
            'canonical_import: import widgets '
            '"github.com/example/widgets-go/v3/pkg/widgets"\n',
            encoding="utf-8",
        )
        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "widgets" / "go"
        content_dir.mkdir(parents=True)

        result = _resolve_go_module(content_dir, repo_root=tmp_path)
        assert result == (
            "widgets",
            "github.com/example/widgets-go/v3/pkg/widgets",
            "github.com/example/widgets-go/v3",
        )

    def test_returns_none_when_no_model_yaml(self, tmp_path):
        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "widgets" / "go"
        content_dir.mkdir(parents=True)

        assert _resolve_go_module(content_dir, repo_root=tmp_path) is None

    def test_prefers_merged_model_yaml_over_gitignored_scout(self, tmp_path):
        """C5 fix: scout/ is gitignored (a fresh checkout/CI box never has it), so
        merged/model.yaml -- git-tracked -- must be checked first. Both files present
        here with DIFFERENT content proves merged actually wins, not just "happens to
        agree with scout"."""
        go_dir = tmp_path / "knowledge" / "widgets" / "go"
        (go_dir / "merged").mkdir(parents=True)
        (go_dir / "scout").mkdir(parents=True)
        (go_dir / "merged" / "model.yaml").write_text(
            'package_name: github.com/example/widgets-go/v9\n'
            'canonical_import: import widgets '
            '"github.com/example/widgets-go/v9/pkg/widgets"\n',
            encoding="utf-8",
        )
        (go_dir / "scout" / "model.yaml").write_text(
            'package_name: github.com/example/widgets-go/v3\n'
            'canonical_import: import widgets '
            '"github.com/example/widgets-go/v3/pkg/widgets"\n',
            encoding="utf-8",
        )
        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "widgets" / "go"
        content_dir.mkdir(parents=True)

        result = _resolve_go_module(content_dir, repo_root=tmp_path)
        assert result == (
            "widgets",
            "github.com/example/widgets-go/v9/pkg/widgets",
            "github.com/example/widgets-go/v9",
        ), "merged/model.yaml must win when both merged and scout exist"

    def test_falls_back_to_scout_when_merged_lacks_the_fields(self, tmp_path):
        """Today's real portfolio state: merged/model.yaml exists (every product has
        one) but does not carry canonical_import/package_name -- only scout does."""
        go_dir = tmp_path / "knowledge" / "widgets" / "go"
        (go_dir / "merged").mkdir(parents=True)
        (go_dir / "scout").mkdir(parents=True)
        (go_dir / "merged" / "model.yaml").write_text(
            "family: widgets\nplatform: go\n", encoding="utf-8",
        )
        (go_dir / "scout" / "model.yaml").write_text(
            'package_name: github.com/example/widgets-go/v3\n'
            'canonical_import: import widgets '
            '"github.com/example/widgets-go/v3/pkg/widgets"\n',
            encoding="utf-8",
        )
        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "widgets" / "go"
        content_dir.mkdir(parents=True)

        result = _resolve_go_module(content_dir, repo_root=tmp_path)
        assert result == (
            "widgets",
            "github.com/example/widgets-go/v3/pkg/widgets",
            "github.com/example/widgets-go/v3",
        )


class TestFindModuleReplacePath:
    """C5 fix: resolve *family*'s own clone directly instead of scanning every
    directory under the clone cache."""

    def test_resolves_the_families_own_clone_directly(self, tmp_path):
        module_path = "github.com/example/widgets-go/v3"
        clone_dir = tmp_path / "aspose_widgets_go"
        clone_dir.mkdir(parents=True)
        (clone_dir / "go.mod").write_text(f"module {module_path}\n\ngo 1.24\n", encoding="utf-8")
        # A decoy clone for an unrelated product that happens to depend on the same
        # module path -- proves the lookup targets THIS family's clone, not any match.
        decoy_dir = tmp_path / "aspose_other_go"
        decoy_dir.mkdir(parents=True)
        (decoy_dir / "go.mod").write_text(
            f"module github.com/example/other-go\n\nrequire {module_path} v3.0.0\n", encoding="utf-8",
        )

        result = _find_module_replace_path(module_path, family="widgets", clone_cache_root=tmp_path)
        assert result == str(clone_dir).replace("\\", "/")

    def test_falls_back_to_scanning_when_the_familys_clone_lacks_the_module(self, tmp_path):
        module_path = "github.com/example/widgets-go/v3"
        # widgets' own clone exists but doesn't reference this module at all.
        own_dir = tmp_path / "aspose_widgets_go"
        own_dir.mkdir(parents=True)
        (own_dir / "go.mod").write_text("module github.com/example/widgets-go\n\ngo 1.24\n", encoding="utf-8")
        # A different clone actually has it.
        other_dir = tmp_path / "aspose_other_go"
        other_dir.mkdir(parents=True)
        (other_dir / "go.mod").write_text(f"module {module_path}\n\ngo 1.24\n", encoding="utf-8")

        result = _find_module_replace_path(module_path, family="widgets", clone_cache_root=tmp_path)
        assert result == str(other_dir).replace("\\", "/")

    def test_returns_none_when_nothing_matches(self, tmp_path):
        assert _find_module_replace_path(
            "github.com/example/nowhere", family="widgets", clone_cache_root=tmp_path,
        ) is None
