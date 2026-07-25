"""Tests for scripts/pipeline/scout.py — core utility functions and data structures."""

import hashlib
from pathlib import Path

# sys.path is set by tests/conftest.py — no manual insert needed here.
import scout


class TestPlatformToLang:
    def test_all_platforms_present(self):
        expected = {"python", "net", "dotnet", "java", "cpp", "typescript", "javascript", "nodejs", "go", "rust"}
        assert set(scout.PLATFORM_TO_LANG.keys()) == expected

    def test_nodejs_maps_to_javascript(self):
        assert scout.PLATFORM_TO_LANG["nodejs"] == "javascript"

    def test_dotnet_maps_to_csharp(self):
        assert scout.PLATFORM_TO_LANG["dotnet"] == "csharp"

    def test_net_maps_to_csharp(self):
        assert scout.PLATFORM_TO_LANG["net"] == "csharp"


class TestNodeTypeMaps:
    def test_class_types_has_required_languages(self):
        for lang in ["java", "csharp", "javascript", "typescript", "cpp", "python"]:
            assert lang in scout._CLASS_TYPES, f"Missing {lang} in _CLASS_TYPES"
            assert len(scout._CLASS_TYPES[lang]) > 0

    def test_func_types_has_required_languages(self):
        for lang in ["java", "csharp", "javascript", "typescript", "cpp", "python"]:
            assert lang in scout._FUNC_TYPES, f"Missing {lang} in _FUNC_TYPES"

    def test_csharp_includes_struct_and_record(self):
        cs_types = scout._CLASS_TYPES["csharp"]
        assert "struct_declaration" in cs_types
        assert "record_declaration" in cs_types

    def test_typescript_includes_interface_and_type_alias(self):
        ts_types = scout._CLASS_TYPES["typescript"]
        assert "interface_declaration" in ts_types
        assert "type_alias_declaration" in ts_types


class TestCollectNodes:
    def test_with_empty_set(self):
        # Should not crash with empty type_names
        class MockNode:
            def __init__(self):
                self.type = "foo"
                self.children = []
        result = scout.collect_nodes(MockNode(), set())
        assert result == []

    def test_collects_matching(self):
        class MockNode:
            def __init__(self, type_name, children=None):
                self.type = type_name
                self.children = children or []

        root = MockNode("root", [
            MockNode("class_declaration", [
                MockNode("method_declaration"),
            ]),
            MockNode("function_declaration"),
        ])
        classes = scout.collect_nodes(root, {"class_declaration"})
        assert len(classes) == 1
        assert classes[0].type == "class_declaration"


class TestClaimIdGeneration:
    def test_deterministic(self):
        """Claim IDs should be deterministic for the same text."""
        text = "The Scene class provides an open method"
        h1 = hashlib.sha256(text.encode()).hexdigest()[:6]
        h2 = hashlib.sha256(text.encode()).hexdigest()[:6]
        assert h1 == h2

    def test_different_text_different_id(self):
        t1 = "Scene class"
        t2 = "Mesh class"
        h1 = hashlib.sha256(t1.encode()).hexdigest()[:6]
        h2 = hashlib.sha256(t2.encode()).hexdigest()[:6]
        assert h1 != h2


class TestFileExtensions:
    def test_has_python(self):
        assert ".py" in scout._FILE_EXTENSIONS.values() or \
               any(v == ".py" for v in scout._FILE_EXTENSIONS.values())

    def test_mapping_exists(self):
        assert len(scout._FILE_EXTENSIONS) > 0


class TestNotImplPatterns:
    def test_patterns_exist(self):
        assert len(scout._NOT_IMPL_PATTERNS) > 0

    def test_python_pattern(self):
        assert "python" in scout._NOT_IMPL_PATTERNS
        pattern = scout._NOT_IMPL_PATTERNS["python"]
        assert pattern.search("raise NotImplementedError")

    def test_csharp_pattern(self):
        assert "csharp" in scout._NOT_IMPL_PATTERNS
        pattern = scout._NOT_IMPL_PATTERNS["csharp"]
        assert pattern.search("throw new NotImplementedException()")


def _make_snippet(source_file, classes_used, code=""):
    """Helper: build a minimal snippet dict matching extraction/snippets.py schema."""
    return {
        "id": "snippet_001",
        "file": "snippet_001.py",       # output filename — never starts with "test"
        "source_file": source_file,     # origin path — what has_tests must check
        "source_function": "test_fn",
        "source_line": 1,
        "language": "python",
        "code": code or f"# uses {', '.join(classes_used)}\n",
        "valid": True,
        "classes_used": list(classes_used),
        "methods_used": [],
        "formats_referenced": [],
    }


def _run_coverage(classes_dicts, snippets):
    """Run _build_coverage on a minimal fake Scout and return coverage list."""
    from extraction.scout import Scout

    class FakeScout:
        _SNIPPET_TEST_DIRS = Scout._SNIPPET_TEST_DIRS

        def _build_coverage(self):
            Scout._build_coverage(self)

    fake = FakeScout()
    fake.classes = classes_dicts
    fake.snippets = snippets
    fake.coverage = []
    fake._build_coverage()
    return {e["class"]: e for e in fake.coverage}


class TestBuildCoverageHasTests:
    """Regression tests for has_tests field in coverage_matrix.

    Primary bug (Fix 1E): _build_coverage was checking s["file"] (output
    filename like "snippet_001.py") instead of s["source_file"] (origin path
    like "tests/test_x.py"), causing has_tests to be universally False.

    Secondary fix: class matching now uses s["classes_used"] (pre-computed
    exact list) instead of a case-insensitive prose scan.
    """

    def _cls(self, name):
        return {"name": name, "file": f"{name}.py", "kind": "class",
                "methods": [], "properties": [], "doc": "", "enum_members": []}

    def test_output_file_never_starts_with_test(self):
        """Confirm the bug was real: output filenames start with 'snippet_'."""
        snip = _make_snippet("tests/test_scene.py", ["Scene"])
        assert not snip["file"].startswith(("test", "tests"))

    def test_has_tests_true_for_tests_directory(self):
        cov = _run_coverage([self._cls("Scene")],
                            [_make_snippet("tests/test_scene.py", ["Scene"])])
        assert cov["Scene"]["has_tests"] is True

    def test_has_tests_true_for_test_directory(self):
        """Snippets from a 'test/' directory (no plural) also count."""
        cov = _run_coverage([self._cls("Scene")],
                            [_make_snippet("test/SceneTest.java", ["Scene"])])
        assert cov["Scene"]["has_tests"] is True

    def test_has_tests_false_for_examples_directory(self):
        cov = _run_coverage([self._cls("Scene")],
                            [_make_snippet("examples/scene_example.py", ["Scene"])])
        assert cov["Scene"]["has_tests"] is False

    def test_has_tests_false_for_readme(self):
        cov = _run_coverage([self._cls("Scene")],
                            [_make_snippet("README.md", ["Scene"])])
        assert cov["Scene"]["has_tests"] is False

    def test_has_tests_false_when_class_not_in_classes_used(self):
        """Class must be in snippet's classes_used, not merely mentioned in prose."""
        snip = _make_snippet("tests/test_scene.py", ["Mesh"],
                             code="# scene node transform matrix\ndef test(): pass")
        cov = _run_coverage([self._cls("Scene"), self._cls("Mesh")], [snip])
        assert cov["Scene"]["has_tests"] is False  # not in classes_used
        assert cov["Mesh"]["has_tests"] is True    # is in classes_used

    def test_has_tests_no_false_positive_from_generic_names(self):
        """Generic class names (Node, Scene, Matrix) in prose must not trigger."""
        snip = _make_snippet(
            "tests/test_transforms.py",
            classes_used=["Transform"],
            code="# Use a node to transform the scene matrix\ndef test(): pass"
        )
        cov = _run_coverage(
            [self._cls("Node"), self._cls("Scene"), self._cls("Matrix"),
             self._cls("Transform")],
            [snip]
        )
        assert cov["Node"]["has_tests"] is False
        assert cov["Scene"]["has_tests"] is False
        assert cov["Matrix"]["has_tests"] is False
        assert cov["Transform"]["has_tests"] is True

    def test_has_tests_multiple_classes_same_snippet(self):
        """A single test snippet can mark multiple classes as tested."""
        snip = _make_snippet("tests/test_3mf.py", ["Scene", "Node", "Mesh"])
        cov = _run_coverage(
            [self._cls("Scene"), self._cls("Node"), self._cls("Mesh"),
             self._cls("Camera")],
            [snip]
        )
        assert cov["Scene"]["has_tests"] is True
        assert cov["Node"]["has_tests"] is True
        assert cov["Mesh"]["has_tests"] is True
        assert cov["Camera"]["has_tests"] is False  # not in this snippet

    def test_has_tests_false_with_no_snippets(self):
        cov = _run_coverage([self._cls("Scene")], [])
        assert cov["Scene"]["has_tests"] is False

    def test_function_kind_excluded_from_coverage(self):
        """Entries with kind='function' are skipped by _build_coverage."""
        cls = self._cls("helper_fn")
        cls["kind"] = "function"
        cov = _run_coverage([cls], [_make_snippet("tests/test_x.py", ["helper_fn"])])
        assert "helper_fn" not in cov
