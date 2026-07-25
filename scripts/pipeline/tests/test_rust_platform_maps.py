"""Tests for Rust platform support in the reference/eval/validation layers
(cells/rust onboarding C2, 2026-07-25).

C1 (test_rust_extraction.py) proved the scout can extract a Rust crate.
This module locks the downstream layers that turn that surface into pages:

- lib/reference_filter: rust kind allowlist; enum_item addition to the shared
  _ENUM_KINDS must not leak into other platforms' filters (their grammars
  never emit enum_item, and their allowlists stay disjoint from rust kinds).
- batch_reference: category labels (Struct/Enum/Trait), module grouping.
- snippets: #[test] fns inline in src files + examples/ main().
- install tooling: cargo add + Cargo git-dependency parsing/detection.
- eval config + code_syntax_check: fence-lang maps and real tree-sitter
  parsing for rust blocks.
"""

import sys
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
import scout
from lib.reference_filter import _passes_platform_scope, filter_api_surface

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import batch_reference as _br

FIXTURE = Path(__file__).parent / "fixtures" / "rust_crate"


def _entry(name="Workbook", kind="struct_item", file="src/workbook.rs", **kw):
    e = {"name": name, "kind": kind, "file": file, "visibility": "public"}
    e.update(kw)
    return e


# ---------------------------------------------------------------------------
# lib/reference_filter
# ---------------------------------------------------------------------------


class TestRustReferenceFilter:
    def test_rust_kinds_pass(self):
        for kind in ("struct_item", "enum_item", "trait_item", "union_item"):
            assert _passes_platform_scope(_entry(kind=kind), "rust"), kind

    def test_function_kind_excluded(self):
        assert not _passes_platform_scope(_entry(kind="function"), "rust")

    def test_internal_path_excluded(self):
        e = _entry(file="src/internal/hidden.rs")
        assert not _passes_platform_scope(e, "rust")

    def test_underscore_name_excluded(self):
        assert not _passes_platform_scope(_entry(name="_Private"), "rust")

    def test_internal_visibility_filtered(self):
        entries = [_entry(), _entry(name="VendorType", visibility="internal")]
        kept = filter_api_surface(entries, "rust")
        assert [e["name"] for e in kept] == ["Workbook"]

    def test_rust_kinds_do_not_pass_other_platforms(self):
        """Cross-grammar disjointness: rust kinds never render for other
        platforms (and their kinds never render for rust)."""
        for platform in ("python", "java", "net", "cpp", "typescript", "go"):
            assert not _passes_platform_scope(
                _entry(kind="struct_item"), platform), platform
            assert not _passes_platform_scope(
                _entry(kind="trait_item"), platform), platform
        assert not _passes_platform_scope(
            _entry(kind="class_declaration"), "rust")

    def test_existing_platform_filters_unchanged(self):
        """Regression: adding enum_item to _ENUM_KINDS must not alter what
        the other platforms' real grammar kinds resolve to."""
        assert _passes_platform_scope(
            _entry(kind="enum_declaration", file="Foo.java"), "java")
        assert _passes_platform_scope(
            _entry(kind="enum_specifier", file="foo.h"), "cpp")
        assert _passes_platform_scope(
            _entry(kind="class_definition", file="foo.py"), "python")


# ---------------------------------------------------------------------------
# batch_reference maps
# ---------------------------------------------------------------------------


class TestRustBatchReference:
    def test_category_labels(self):
        assert _br._category(_entry(kind="struct_item"), "rust") == "Struct"
        assert _br._category(_entry(kind="enum_item"), "rust") == "Enum"
        assert _br._category(_entry(kind="trait_item"), "rust") == "Trait"

    def test_is_enum(self):
        assert _br._is_enum(_entry(kind="enum_item"), "rust") is True
        assert _br._is_enum(_entry(kind="struct_item"), "rust") is False

    def test_platform_lang_map(self):
        assert _br._PLATFORM_TO_LANG["rust"] == "rust"

    def test_class_kinds(self):
        assert _br._CLASS_KINDS_BY_PLATFORM["rust"] == {
            "struct_item", "enum_item", "trait_item", "union_item"}

    def test_group_key_module(self):
        e = _entry(file="src/formats/xlsx.rs")
        assert _br._derive_group_key(e, "cells", "rust") == "formats"

    def test_group_key_root_is_core(self):
        e = _entry(file="src/workbook.rs")
        assert _br._derive_group_key(e, "cells", "rust") == "core"


# ---------------------------------------------------------------------------
# Snippets: inline #[test] fns + examples/ main()
# ---------------------------------------------------------------------------


class TestRustSnippets:
    def test_fixture_crate_snippets(self):
        from extraction.snippets import extract_snippets
        parser = scout.get_parser("rust")
        snippets = extract_snippets(
            parser, "rust", FIXTURE / "src", FIXTURE, [], [])
        fns = {s["source_function"] for s in snippets}
        assert "coord_roundtrip" in fns  # inline #[cfg(test)] mod tests fn
        assert "main" in fns             # examples/basic.rs
        for s in snippets:
            assert s["language"] == "rust"
            assert s["valid"] is True


# ---------------------------------------------------------------------------
# Install tooling
# ---------------------------------------------------------------------------


class TestRustInstallTooling:
    GIT_DEP_INSTALL_MD = """# Install aspose-cells-foss-rust

```
# Cargo.toml
[dependencies]
aspose-cells-foss-rust = { git = "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust" }
```
"""

    CARGO_ADD_INSTALL_MD = """# Install

```
cargo add aspose-cells-foss-rust@26.7.0
```
"""

    def test_detect_platform_type(self):
        from commands.content.install_block_updater import _detect_platform_type
        assert _detect_platform_type("rust") == "rust"

    def test_parse_git_dependency_form(self, tmp_path):
        from commands.content.install_block_updater import _parse_install_md
        p = tmp_path / "install.md"
        p.write_text(self.GIT_DEP_INSTALL_MD, encoding="utf-8")
        info = _parse_install_md(p)
        assert info["package_name"] == "aspose-cells-foss-rust"

    def test_parse_cargo_add_form(self, tmp_path):
        from commands.content.install_block_updater import _parse_install_md
        p = tmp_path / "install.md"
        p.write_text(self.CARGO_ADD_INSTALL_MD, encoding="utf-8")
        info = _parse_install_md(p)
        assert info["package_name"] == "aspose-cells-foss-rust"
        assert info["version"] == "26.7.0"

    def test_block_contains_install(self):
        from commands.content.install_block_updater import _block_contains_install
        info = {"package_name": "aspose-cells-foss-rust"}
        assert _block_contains_install(
            self.GIT_DEP_INSTALL_MD, info, "rust") is True
        assert _block_contains_install(
            self.CARGO_ADD_INSTALL_MD, info, "rust") is True
        assert _block_contains_install(
            "```\npip install foo\n```", info, "rust") is False

    def test_install_recipe_maps(self):
        from content_eval.evaluators.install_recipe import (
            _INSTALL_PROSE_RE, _PKG_NAME_RE, _PLATFORM_PKG_MANAGERS)
        assert _PLATFORM_PKG_MANAGERS["rust"] == {"cargo"}
        m = _PKG_NAME_RE.search("cargo add aspose-cells-foss-rust")
        assert m and m.group(1) == "aspose-cells-foss-rust"
        assert _INSTALL_PROSE_RE.search("[dependencies]")


# ---------------------------------------------------------------------------
# Eval config + syntax checking
# ---------------------------------------------------------------------------


class TestRustEvalConfig:
    def test_lang_to_platform(self):
        from content_eval.config import LANG_TO_PLATFORM
        assert LANG_TO_PLATFORM["rust"] == "rust"
        assert LANG_TO_PLATFORM["rs"] == "rust"

    def test_expected_langs(self):
        from content_eval.config import PLATFORM_EXPECTED_LANGS
        assert PLATFORM_EXPECTED_LANGS["rust"] == {"rust", "rs"}

    def test_foreign_patterns_registered(self):
        from content_eval.config import (PLATFORM_FOREIGN_PATTERNS,
                                         PROSE_FOREIGN_PATTERNS)
        assert "rust" in PLATFORM_FOREIGN_PATTERNS
        assert "rust" in PROSE_FOREIGN_PATTERNS

    def test_foreign_patterns_allow_idiomatic_rust(self):
        """`self.field` (even assigned) is idiomatic Rust — no rust foreign
        pattern may match it."""
        import re
        from content_eval.config import PLATFORM_FOREIGN_PATTERNS
        rust_code = "fn set_path(&mut self, p: String) { self.path = p; }"
        for pattern, desc in PLATFORM_FOREIGN_PATTERNS["rust"]:
            assert not re.search(pattern, rust_code), desc

    def test_fence_fixer_primary_lang(self):
        from content_eval.remediation.fixers.code_fence_lang import (
            _PLATFORM_PRIMARY_LANG, _SHELL_INDICATORS)
        assert _PLATFORM_PRIMARY_LANG["rust"] == "rust"
        assert _SHELL_INDICATORS.search("cargo add foo")


class TestRustSyntaxChecking:
    def test_code_syntax_check_parser_loads(self):
        from content_eval.evaluators import code_syntax_check as csc
        assert "rust" in csc._TS_LANGS
        parser = csc._ts_parser_for("rust")
        assert parser is not None

    def test_valid_rust_parses_clean(self):
        from content_eval.evaluators import code_syntax_check as csc
        parser = csc._ts_parser_for("rust")
        tree = parser.parse(b"fn main() { println!(\"ok\"); }")
        assert tree.root_node.has_error is False

    def test_broken_rust_flagged(self):
        from content_eval.evaluators import code_syntax_check as csc
        parser = csc._ts_parser_for("rust")
        tree = parser.parse(b"fn main( { let = ; }")
        assert tree.root_node.has_error is True

    def test_smoke_test_maps(self):
        from commands.diagnostics import smoke_test as st
        assert st._PLATFORM_LANGS["rust"] == frozenset({"rust", "rs"})
        assert st._TS_LANG_MAP["rust"] == "rust"
        assert st._LANG_DISPLAY["rust"] == "Rust"
        assert st._ts_parser_for("rust") is not None


# ---------------------------------------------------------------------------
# Knowledge-layer casing / coverage policy
# ---------------------------------------------------------------------------


class TestRustKnowledgePolicy:
    def test_coverage_concrete_only(self):
        from content_eval.evaluators.coverage import CONCRETE_ONLY_PLATFORMS
        assert "rust" in CONCRETE_ONLY_PLATFORMS

    def test_promote_snake_inference(self):
        """promote's name-inference must treat rust as snake_case: set_x
        setters get inferred docs; nothing crashes on bare getters."""
        from commands.knowledge.promote import _apply_godoc_fallback
        api = [{
            "name": "Workbook",
            "methods": [
                {"name": "set_path", "params": [{"name": "p"}], "doc": ""},
                {"name": "path", "params": [], "return_type": "String", "doc": ""},
            ],
            "properties": [],
        }]
        count = _apply_godoc_fallback(api, "rust")
        assert count >= 1
        set_path = api[0]["methods"][0]
        assert set_path["doc"], "set_path should receive inferred doc"
        assert set_path.get("doc_source") == "name_inference"
