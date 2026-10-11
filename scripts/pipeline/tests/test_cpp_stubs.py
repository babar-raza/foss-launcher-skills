"""Tests for Scout._detect_cpp_stubs() — C++ empty-body and trivial-return detection.

Covers:
- Empty-body stub: void Foo() {}
- Trivial return stubs: return false/nullptr/0/NULL
- Normal implementations are NOT flagged
- _iter_nodes is module-level (no redefinition per file)
"""

import tempfile
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import scout
from extraction.scout import _iter_nodes, Scout


# ---------------------------------------------------------------------------
# Unit tests for _iter_nodes (module-level helper)
# ---------------------------------------------------------------------------

class TestIterNodes:
    """_iter_nodes must be importable at module level (not defined inside a loop)."""

    def test_is_callable(self):
        assert callable(_iter_nodes)

    def test_yields_root_when_type_matches(self):
        parser = scout.get_parser("cpp")
        tree = parser.parse(b"int x = 0;")
        nodes = list(_iter_nodes(tree.root_node, "translation_unit"))
        assert len(nodes) >= 1

    def test_yields_nothing_for_nonexistent_type(self):
        parser = scout.get_parser("cpp")
        tree = parser.parse(b"int x = 0;")
        nodes = list(_iter_nodes(tree.root_node, "nonexistent_type_xyz"))
        assert nodes == []

    def test_finds_nested_nodes(self):
        parser = scout.get_parser("cpp")
        code = b"class Foo { void bar() {} };"
        tree = parser.parse(code)
        func_defs = list(_iter_nodes(tree.root_node, "function_definition"))
        assert len(func_defs) >= 1


# ---------------------------------------------------------------------------
# Helpers to create a minimal Scout instance for C++ limitation detection
# ---------------------------------------------------------------------------

def _make_cpp_scout(tmp_path: Path, cpp_source: str) -> Scout:
    """Create a Scout instance with a synthetic C++ file and run limitation detection."""
    # Write a .cpp file in a temp pkg_root
    src_file = tmp_path / "src" / "stub.cpp"
    src_file.parent.mkdir(parents=True)
    src_file.write_text(cpp_source, encoding="utf-8")

    # Minimal Scout: init just enough state to call _detect_cpp_stubs
    s = Scout.__new__(Scout)
    s.language = "cpp"
    s.pkg_root = tmp_path / "src"
    s.repo = tmp_path
    s.parser = scout.get_parser("cpp")
    s.limitations = []
    s.claims = []

    def _add_claim(kind, text, src, line):
        s.claims.append({"kind": kind, "text": text, "source": src, "line": line})

    s._add_claim = _add_claim
    s._detect_cpp_stubs()
    return s


# ---------------------------------------------------------------------------
# Empty-body stub detection
# ---------------------------------------------------------------------------

class TestEmptyBodyStubs:

    def test_empty_void_function_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "void ExportScene() {}")
        assert any("ExportScene" in lim["text"] for lim in s.limitations), (
            "Expected ExportScene empty-body stub to be flagged"
        )

    def test_empty_body_limitation_has_required_fields(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "void DoSomething() {}")
        lim = next(l for l in s.limitations if "DoSomething" in l["text"])
        assert "file" in lim
        assert "line" in lim
        assert "method" in lim

    def test_non_empty_function_not_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "int Add(int a, int b) { return a + b; }")
        flagged = [l for l in s.limitations if "Add" in l["text"]]
        assert flagged == [], "Non-stub function must not be flagged"

    def test_function_with_comment_only_flagged(self, tmp_path):
        # A body with only a comment is still an empty stub
        s = _make_cpp_scout(tmp_path, "void Render() { /* TODO */ }")
        assert any("Render" in l["text"] for l in s.limitations)


# ---------------------------------------------------------------------------
# Trivial-return stub detection
# ---------------------------------------------------------------------------

class TestTrivialReturnStubs:

    def test_return_false_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "bool SaveToPdf(const char* path) { return false; }")
        assert any("SaveToPdf" in l["text"] for l in s.limitations)

    def test_return_nullptr_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "Scene* Load(const char* path) { return nullptr; }")
        assert any("Load" in l["text"] for l in s.limitations)

    def test_nodiscard_override_member_flagged(self, tmp_path):
        # field_identifier (class member context) must be detected
        code = "class Shape { [[nodiscard]] IPresentation* presentation() override { return nullptr; } };"
        s = _make_cpp_scout(tmp_path, code)
        assert any("presentation" in l["text"] for l in s.limitations), (
            "[[nodiscard]] override member function returning nullptr must be flagged"
        )

    def test_return_zero_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "int GetCount() { return 0; }")
        assert any("GetCount" in l["text"] for l in s.limitations)

    def test_return_null_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "void* GetHandle() { return NULL; }")
        assert any("GetHandle" in l["text"] for l in s.limitations)

    def test_real_return_value_not_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "int GetVersion() { return 2; }")
        flagged = [l for l in s.limitations if "GetVersion" in l["text"]]
        assert flagged == [], "Genuine return value must not be flagged"

    def test_return_true_not_flagged(self, tmp_path):
        s = _make_cpp_scout(tmp_path, "bool IsSupported() { return true; }")
        flagged = [l for l in s.limitations if "IsSupported" in l["text"]]
        assert flagged == [], "return true is not a stub pattern"
