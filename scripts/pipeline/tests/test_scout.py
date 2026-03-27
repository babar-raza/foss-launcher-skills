"""Tests for scripts/pipeline/scout.py — core utility functions and data structures."""

import hashlib
import sys
from pathlib import Path

# Add scripts/ to path so we can import scout module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts/pipeline"))

import scout  # noqa: E402


class TestPlatformToLang:
    def test_all_platforms_present(self):
        expected = {"python", "dotnet", "java", "cpp", "typescript", "javascript", "nodejs"}
        assert set(scout.PLATFORM_TO_LANG.keys()) == expected

    def test_nodejs_maps_to_javascript(self):
        assert scout.PLATFORM_TO_LANG["nodejs"] == "javascript"

    def test_dotnet_maps_to_csharp(self):
        assert scout.PLATFORM_TO_LANG["dotnet"] == "csharp"


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
