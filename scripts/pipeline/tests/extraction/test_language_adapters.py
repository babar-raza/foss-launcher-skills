"""Adapter contract tests for extraction/lang/ (TC-MT040-42).

Covers the shared interface every one of the 7 language modules (python,
rust, csharp, typescript, java, cpp, go) exposes -- see
extraction/lang/__init__.py's module docstring for the full contract.
Byte-parity against the PRE-refactor python/rust behavior is covered
separately by tests/test_extraction_goldens.py; this file is about the
adapter *contract* itself (every module shaped the same way) plus targeted
behavior checks for each function, including the C#/typescript/java/cpp/go
paths the goldens file doesn't touch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from content_eval.evaluators import _reachability
from extraction import lang

ALL_LANGUAGES = ("python", "rust", "csharp", "typescript", "java", "cpp", "go")
# TC-MT040-11 gave typescript a real export_surface() implementation --
# removed from this "no signal yet" list; see test_typescript_export_surface.py
# for its own dedicated behavior coverage.
NO_SIGNAL_LANGUAGES = ("java", "cpp", "go")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_all_caches():
    """Every adapter that caches (python/rust/csharp) must start and end
    each test with a clean slate -- mirrors
    tests/content_eval/test_code_reachability.py's own autouse pattern."""
    _reachability.clear_caches()
    yield
    _reachability.clear_caches()


# ---------------------------------------------------------------------------
# 1. Interface completeness -- every module exposes the same shape
# ---------------------------------------------------------------------------

class TestAdapterInterfaceCompleteness:

    @pytest.mark.parametrize("language", ALL_LANGUAGES)
    def test_module_registered_in_lang_languages(self, language):
        assert language in lang.LANGUAGES
        assert lang.get(language) is lang.LANGUAGES[language]

    @pytest.mark.parametrize("language", ALL_LANGUAGES)
    def test_exposes_all_four_functions(self, language):
        mod = lang.get(language)
        for fn_name in ("declaration_kinds", "doc_anchor", "parse_doc",
                        "export_surface", "clear_cache"):
            assert callable(getattr(mod, fn_name, None)), (
                f"{language}.{fn_name} missing or not callable"
            )

    @pytest.mark.parametrize("language", ALL_LANGUAGES)
    def test_declaration_kinds_shape(self, language):
        mod = lang.get(language)
        kinds = mod.declaration_kinds()
        assert isinstance(kinds, dict)
        for key in ("class_types", "func_types", "module_types", "import_types"):
            assert key in kinds, f"{language}.declaration_kinds() missing {key!r}"
            assert isinstance(kinds[key], (set, frozenset))

    @pytest.mark.parametrize("language", ALL_LANGUAGES)
    def test_declaration_kinds_matches_tree_helpers(self, language):
        """declaration_kinds() must be a faithful per-language subset of
        tree_helpers' own cross-language dicts, not a reimplementation."""
        from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES

        mod = lang.get(language)
        kinds = mod.declaration_kinds()
        assert kinds["class_types"] == _CLASS_TYPES.get(language, set())
        assert kinds["func_types"] == _FUNC_TYPES.get(language, set())

    def test_get_unrecognized_language_returns_none(self):
        assert lang.get("cobol") is None

    def test_clear_all_caches_does_not_raise(self):
        lang.clear_all_caches()


# ---------------------------------------------------------------------------
# 2. export_surface -- (None, None) for languages with no signal yet
# ---------------------------------------------------------------------------

class TestExportSurfaceNoSignalLanguages:

    @pytest.mark.parametrize("language", NO_SIGNAL_LANGUAGES)
    def test_returns_none_none_unconditionally(self, language, tmp_path):
        mod = lang.get(language)
        names, root = mod.export_surface(tmp_path, tmp_path)
        assert names is None
        assert root is None

    @pytest.mark.parametrize("language", NO_SIGNAL_LANGUAGES)
    def test_returns_none_none_even_with_real_looking_content(self, language, tmp_path):
        """Fail-safe: even a directory that superficially looks like a real
        repo must still resolve to (None, None) -- these languages have no
        implementation, not a broken one that returns empty results."""
        (tmp_path / "lib.rs").write_text("pub use api::Foo;\n", encoding="utf-8")
        (tmp_path / "__init__.py").write_text("__all__ = ['Foo']\n", encoding="utf-8")
        mod = lang.get(language)
        names, root = mod.export_surface(tmp_path, tmp_path)
        assert (names, root) == (None, None)


# ---------------------------------------------------------------------------
# 3. export_surface -- python (matches old _python_top_level_exports)
# ---------------------------------------------------------------------------

class TestExportSurfacePython:

    def test_simple_top_level_init(self, tmp_path):
        pkg_root = tmp_path / "aspose_barcode_foss"
        _write(pkg_root / "__init__.py", "__all__ = ['generate', 'Barcode']\n")
        names, root = lang.python.export_surface(tmp_path, pkg_root)
        assert names == {"generate", "Barcode"}
        assert root == pkg_root

    def test_namespace_parent_layout(self, tmp_path):
        """The real words/python case: pkg_root resolves to an outer
        empty-__init__.py directory, with the actual __all__ one level down
        in exactly one subpackage."""
        pkg_root = tmp_path / "aspose"
        _write(pkg_root / "__init__.py", "")
        _write(pkg_root / "words_foss" / "__init__.py",
               "__all__ = ['Document', 'SaveFormat']\n")
        names, root = lang.python.export_surface(tmp_path, pkg_root)
        assert names == {"Document", "SaveFormat"}
        assert root == pkg_root / "words_foss"

    def test_no_all_anywhere_returns_none_none(self, tmp_path):
        pkg_root = tmp_path / "aspose_x"
        _write(pkg_root / "__init__.py", "from .a import A\n")
        names, root = lang.python.export_surface(tmp_path, pkg_root)
        assert names is None
        assert root is None

    def test_matches_old_module_level_wrapper(self, tmp_path):
        """api_surface._python_top_level_exports (the thin wrapper kept for
        backward-compat imports) must produce identical results to calling
        the adapter directly."""
        from extraction.api_surface import _python_top_level_exports

        pkg_root = tmp_path / "pkg"
        _write(pkg_root / "__init__.py", "__all__ = ['A', 'B']\n")
        direct = lang.python.export_surface(tmp_path, pkg_root)
        via_wrapper = _python_top_level_exports(pkg_root)
        assert direct == via_wrapper


# ---------------------------------------------------------------------------
# 4. export_surface -- rust (matches old _rust_reexported_names)
# ---------------------------------------------------------------------------

class TestExportSurfaceRust:

    def test_brace_form(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "lib.rs", "pub use api::{Workbook, Worksheet};\n")
        names, root = lang.rust.export_surface(tmp_path, pkg_root)
        assert names == {"Workbook", "Worksheet"}
        assert root == pkg_root

    def test_glob_returns_none(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "lib.rs", "pub use api::*;\n")
        names, root = lang.rust.export_surface(tmp_path, pkg_root)
        assert names is None

    def test_matches_old_module_level_wrapper(self, tmp_path):
        from extraction.api_surface import _rust_reexported_names

        pkg_root = tmp_path / "src"
        _write(pkg_root / "lib.rs", "pub use api::{A, B};\n")
        direct_names, _ = lang.rust.export_surface(tmp_path, pkg_root)
        via_wrapper = _rust_reexported_names(pkg_root)
        assert direct_names == via_wrapper


# ---------------------------------------------------------------------------
# 5. export_surface -- csharp (NEW to the scout side; polarity-inverted)
# ---------------------------------------------------------------------------

class TestExportSurfaceCsharp:

    def test_internal_class_detected(self, tmp_path):
        _write(tmp_path / "Foo.cs", "internal class Bar { }\n")
        names, root = lang.csharp.export_surface(tmp_path, tmp_path)
        assert names == {"Bar"}
        assert root == tmp_path

    def test_public_class_not_in_internal_set(self, tmp_path):
        _write(tmp_path / "Foo.cs", "public class Bar { }\n")
        names, root = lang.csharp.export_surface(tmp_path, tmp_path)
        assert names == set()

    def test_missing_repo_returns_empty_not_none(self, tmp_path):
        """Matches the original _csharp_internal_names contract exactly:
        unavailable repo -> empty frozenset (never flags anything), not
        None -- csharp's export_surface never returns None for `names`."""
        missing = tmp_path / "does_not_exist"
        names, root = lang.csharp.export_surface(missing, missing)
        assert names == set()


# ---------------------------------------------------------------------------
# 6. doc_anchor
# ---------------------------------------------------------------------------

class _FakeNode:
    """Minimal duck-typed stand-in for a tree-sitter node -- doc_anchor()
    only ever reads .type and .parent."""

    def __init__(self, type_: str, parent: "_FakeNode | None" = None):
        self.type = type_
        self.parent = parent


class TestDocAnchor:

    @pytest.mark.parametrize("language", ["python", "rust", "csharp",
                                           "typescript", "java", "cpp"])
    def test_identity_for_non_go_languages(self, language):
        mod = lang.get(language)
        node = _FakeNode("class_definition")
        assert mod.doc_anchor(node) is node

    def test_go_type_spec_redirects_to_parent(self):
        parent = _FakeNode("type_declaration")
        node = _FakeNode("type_spec", parent=parent)
        assert lang.go.doc_anchor(node) is parent

    def test_go_non_type_spec_is_identity(self):
        node = _FakeNode("function_declaration", parent=_FakeNode("source_file"))
        assert lang.go.doc_anchor(node) is node

    def test_go_type_spec_without_parent_is_identity(self):
        node = _FakeNode("type_spec", parent=None)
        assert lang.go.doc_anchor(node) is node


# ---------------------------------------------------------------------------
# 7. parse_doc -- per-language thin-wrapper cleaning + first-sentence
# ---------------------------------------------------------------------------

class TestParseDoc:

    def test_python(self):
        assert lang.python.parse_doc('"""Represents a document. More detail."""') == \
            {"summary": "Represents a document."}

    def test_python_raw_prefix(self):
        assert lang.python.parse_doc('r"""Raw doc string."""') == \
            {"summary": "Raw doc string."}

    def test_rust(self):
        raw = "/// A workbook.\n/// More detail here."
        assert lang.rust.parse_doc(raw) == {"summary": "A workbook."}

    def test_rust_blank_line_ends_paragraph(self):
        raw = "/// Summary line.\n///\n/// Not part of summary."
        assert lang.rust.parse_doc(raw) == {"summary": "Summary line."}

    def test_csharp_xml_doc(self):
        raw = "/// <summary>\n/// Gets the value.\n/// </summary>"
        result = lang.csharp.parse_doc(raw)
        assert result["summary"] == "Gets the value."

    def test_java_javadoc(self):
        raw = "/** Represents a document.\n * More detail. */"
        assert lang.java.parse_doc(raw) == {"summary": "Represents a document."}

    def test_java_non_javadoc_returns_empty(self):
        assert lang.java.parse_doc("// not javadoc") == {"summary": ""}

    def test_cpp_javadoc_style(self):
        raw = "/** Cell coordinate pair. */"
        assert lang.cpp.parse_doc(raw) == {"summary": "Cell coordinate pair."}

    def test_typescript_jsdoc(self):
        raw = "/** Does a thing. */"
        assert lang.typescript.parse_doc(raw) == {"summary": "Does a thing."}

    def test_go_godoc(self):
        raw = "// Annotation describes an annotation on a page."
        assert lang.go.parse_doc(raw) == \
            {"summary": "Annotation describes an annotation on a page."}

    def test_go_blank_line_ends_paragraph_even_before_content(self):
        """Preserves the original godoc branch's exact quirk: a blank `//`
        line ends the paragraph unconditionally, even before any content has
        been collected (unlike rust/xml_doc, which only stop on a blank
        line AFTER collecting at least one line)."""
        raw = "//\n// This line is never reached."
        assert lang.go.parse_doc(raw) == {"summary": ""}


# ---------------------------------------------------------------------------
# 8. clear_cache -- adapter-level, and via _reachability.clear_caches()
# ---------------------------------------------------------------------------

class TestClearCache:

    def test_python_adapter_clear_cache_reflects_mutation(self, tmp_path):
        pkg_root = tmp_path / "pkg"
        _write(pkg_root / "__init__.py", "__all__ = ['A']\n")
        names, _ = lang.python.export_surface(tmp_path, pkg_root)
        assert names == {"A"}

        _write(pkg_root / "__init__.py", "__all__ = ['A', 'B']\n")
        # Still cached -- stale result until clear_cache().
        names_stale, _ = lang.python.export_surface(tmp_path, pkg_root)
        assert names_stale == {"A"}

        lang.python.clear_cache()
        names_fresh, _ = lang.python.export_surface(tmp_path, pkg_root)
        assert names_fresh == {"A", "B"}

    def test_rust_adapter_clear_cache_reflects_mutation(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "lib.rs", "pub use api::{A};\n")
        names, _ = lang.rust.export_surface(tmp_path, pkg_root)
        assert names == {"A"}

        _write(pkg_root / "lib.rs", "pub use api::{A, B};\n")
        names_stale, _ = lang.rust.export_surface(tmp_path, pkg_root)
        assert names_stale == {"A"}

        lang.rust.clear_cache()
        names_fresh, _ = lang.rust.export_surface(tmp_path, pkg_root)
        assert names_fresh == {"A", "B"}

    def test_reachability_clear_caches_clears_underlying_adapter_cache(
        self, tmp_path, monkeypatch,
    ):
        """The exact pattern from tests/content_eval/test_code_reachability.py
        (mutate, call, mutate again, clear_caches, call again, confirm the
        second result reflects the mutation) -- proving
        content_eval.evaluators._reachability.clear_caches() reaches all the
        way down through this card's new extraction/lang/ adapter cache
        layer, not just its own (family, platform)-keyed layer."""
        repo_dir = tmp_path / "clone" / "aspose_fixture_python"
        pkg_dir = repo_dir / "aspose_fixture"
        pkg_dir.mkdir(parents=True)
        _write(repo_dir / "aspose_fixture" / "__init__.py", "__all__ = ['A']\n")

        import core.clone_cache as clone_cache_mod

        def _fake_path(fam, plat):
            return repo_dir if (fam, plat) == ("fixture", "python") else Path("/nonexistent")

        # Same clone_path monkeypatch pattern as the established precedent in
        # tests/content_eval/test_code_reachability.py::_fake_clone() -- a
        # filesystem I/O boundary mock. Note: check_monkeypatch_lint.py's
        # `# T3-MOCK:` comment only re-labels violations classify_target()
        # already resolves to tier 3 via its literal allowlists; `clone_path`
        # is not in that allowlist, so this site is (correctly, like its
        # sibling) counted as T2 and covered by the regenerated repo-wide
        # baseline instead (scripts/ci/monkeypatch_baseline.json).
        monkeypatch.setattr(clone_cache_mod, "clone_path", _fake_path)

        # "B" is not yet exported -- confirmed unreachable.
        is_unreachable, _reason = _reachability.live_unreachable(
            "B", "fixture", "python", "python")
        assert is_unreachable is True

        # Mutate the fixture to now export "B" too, but do NOT clear caches yet.
        _write(pkg_dir / "__init__.py", "__all__ = ['A', 'B']\n")
        is_unreachable_stale, _reason = _reachability.live_unreachable(
            "B", "fixture", "python", "python")
        assert is_unreachable_stale is True, (
            "expected a STALE cached result before clear_caches() -- if this "
            "fails, caching was silently dropped somewhere in the refactor"
        )

        _reachability.clear_caches()

        is_unreachable_fresh, _reason = _reachability.live_unreachable(
            "B", "fixture", "python", "python")
        assert is_unreachable_fresh is False, (
            "expected clear_caches() to reach the extraction/lang/python.py "
            "adapter's own cache layer, not just _reachability.py's own"
        )
