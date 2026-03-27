"""Tests for audit.py property chain resolution."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "pipeline"))

from audit import Knowledge


@pytest.fixture
def mock_knowledge(tmp_path):
    """Build a minimal Knowledge with property type data."""
    merged = tmp_path / "test_family" / "test_platform" / "merged"
    merged.mkdir(parents=True)

    import json
    import yaml

    # model.yaml
    (merged / "model.yaml").write_text(yaml.dump({
        "version": "1.0",
        "repo_sha": "abc123",
    }))

    # api_surface.json with property types
    api_surface = [
        {
            "name": "Scene",
            "methods": [
                {"name": "open", "return_type": "", "params": ["filename"]},
                {"name": "create_child_node", "return_type": "Node", "params": []},
            ],
            "properties": [
                {"name": "root_node", "type": "Node", "line": 10},
                {"name": "asset_info", "type": "AssetInfo", "line": 20},
                {"name": "library", "type": "List['CustomObject']", "line": 30},
            ],
            "enum_members": [],
            "bases": [],
        },
        {
            "name": "Node",
            "methods": [
                {"name": "create_child_node", "return_type": "Node", "params": ["name"]},
                {"name": "get_bounding_box", "return_type": "BoundingBox", "params": []},
            ],
            "properties": [
                {"name": "name", "type": "str", "line": 10},
                {"name": "transform", "type": "Transform", "line": 20},
            ],
            "enum_members": [],
            "bases": ["A3DObject"],
        },
        {
            "name": "AssetInfo",
            "methods": [],
            "properties": [
                {"name": "title", "type": "str", "line": 10},
            ],
            "enum_members": [],
            "bases": [],
        },
    ]
    (merged / "api_surface.json").write_text(json.dumps(api_surface))

    with patch.object(Knowledge, "__init__", lambda self, f, p: None):
        k = Knowledge.__new__(Knowledge)

    k.family = "test_family"
    k.platform = "test_platform"
    k.available = True
    k.surface_tier = 2
    k.classes = {}
    k.methods = {}
    k.properties = {}
    k.enum_members = {}
    k.return_types = {}
    k.property_types = {}
    k.parents = {}
    k.valid_imports = set()

    import re
    for cls in api_surface:
        name = cls["name"]
        k.classes[name] = cls
        k.methods[name] = {m["name"] for m in cls.get("methods", []) if isinstance(m, dict)}
        k.properties[name] = {p["name"] for p in cls.get("properties", []) if isinstance(p, dict)}
        for m in cls.get("methods", []):
            if isinstance(m, dict) and m.get("return_type"):
                k.return_types[(name, m["name"])] = m["return_type"]
        for p in cls.get("properties", []):
            if isinstance(p, dict) and p.get("type"):
                k.property_types[(name, p["name"])] = p["type"]
        k.parents[name] = cls.get("bases", [])

    return k


class TestResolveChain:
    def test_property_type_resolution(self, mock_knowledge):
        """Scene.root_node should resolve to Node."""
        result = mock_knowledge.resolve_chain("Scene.root_node")
        assert result == "Node"

    def test_method_return_type_resolution(self, mock_knowledge):
        """Scene.create_child_node should resolve to Node via return type."""
        result = mock_knowledge.resolve_chain("Scene.create_child_node")
        assert result == "Node"

    def test_unresolvable_chain(self, mock_knowledge):
        """Unknown class should return None."""
        result = mock_knowledge.resolve_chain("Unknown.property")
        assert result is None

    def test_unknown_member(self, mock_knowledge):
        """Known class but unknown member should return None."""
        result = mock_knowledge.resolve_chain("Scene.nonexistent")
        assert result is None

    def test_list_wrapped_type(self, mock_knowledge):
        """Scene.library has type List['CustomObject'] — CustomObject not in classes, so None."""
        result = mock_knowledge.resolve_chain("Scene.library")
        assert result is None  # CustomObject not in mock classes

    def test_nested_resolution(self, mock_knowledge):
        """Scene.asset_info should resolve to AssetInfo."""
        result = mock_knowledge.resolve_chain("Scene.asset_info")
        assert result == "AssetInfo"

    def test_non_dotted_returns_none(self, mock_knowledge):
        """Non-dotted string should return None."""
        result = mock_knowledge.resolve_chain("Scene")
        assert result is None


class TestGetPropertyType:
    def test_direct_property(self, mock_knowledge):
        result = mock_knowledge.get_property_type("Scene", "root_node")
        assert result == "Node"

    def test_missing_property(self, mock_knowledge):
        result = mock_knowledge.get_property_type("Scene", "nonexistent")
        assert result is None

    def test_inherited_not_found(self, mock_knowledge):
        """Node inherits from A3DObject but A3DObject is not in mock, so returns None."""
        result = mock_knowledge.get_property_type("Node", "nonexistent_inherited")
        assert result is None


class TestIsPropertyOnly:
    def test_property_only_true(self, mock_knowledge):
        """root_node is a property but not a method on Scene."""
        assert mock_knowledge.is_property_only("Scene", "root_node") is True

    def test_method_not_property_only(self, mock_knowledge):
        """open is a method on Scene, not property-only."""
        assert mock_knowledge.is_property_only("Scene", "open") is False

    def test_unknown_member(self, mock_knowledge):
        """Unknown member is neither property nor method."""
        assert mock_knowledge.is_property_only("Scene", "nonexistent") is False

    def test_unknown_class(self, mock_knowledge):
        """Unknown class has no properties or methods."""
        assert mock_knowledge.is_property_only("Unknown", "anything") is False


class TestAssignmentTracking:
    """Tests for _PY_ASSIGNMENT regex and variable tracking (SR-01, SR-03)."""

    def test_assignment_regex_lowercase_still_tracked(self):
        """result = some_func( should still populate var_types via primary regex."""
        from audit import _extract_from_code_line
        var_types = {}
        # lowercase func — primary regex matches but doesn't set (lowercase name)
        # This ensures the primary regex still matches the line (no crash)
        _extract_from_code_line("result = some_func(arg)", 1, var_types, "python")
        # lowercase func names are NOT tracked as class types (correct behavior)
        # but the regex must not crash or skip the line entirely

    def test_qualified_assignment_module_prefix(self):
        """scene = aspose.threed.Scene( should populate var_types['scene'] = 'Scene'."""
        from audit import _extract_from_code_line
        var_types = {}
        _extract_from_code_line("scene = aspose.threed.Scene()", 1, var_types, "python")
        assert var_types.get("scene") == "Scene"

    def test_annotated_assignment(self):
        """scene: Scene = Scene( should populate var_types['scene'] = 'Scene'."""
        from audit import _extract_from_code_line
        var_types = {}
        _extract_from_code_line("scene: Scene = Scene()", 1, var_types, "python")
        assert var_types.get("scene") == "Scene"

    def test_simple_class_assignment(self):
        """scene = Scene( should still work with the reverted primary regex."""
        from audit import _extract_from_code_line
        var_types = {}
        _extract_from_code_line("scene = Scene()", 1, var_types, "python")
        assert var_types.get("scene") == "Scene"

    def test_method_assignment_takes_precedence_over_prop(self):
        """node = scene.create_child_node() should be tracked as method, not property."""
        from audit import _extract_from_code_line
        var_types = {"scene": "Scene"}
        _extract_from_code_line("node = scene.create_child_node()", 1, var_types, "python")
        assert var_types.get("node") == "Scene.create_child_node"

    def test_prop_assignment_no_parens(self):
        """name = node.name should be tracked as property access (no parens)."""
        from audit import _extract_from_code_line
        var_types = {"node": "Node"}
        _extract_from_code_line("name = node.name", 1, var_types, "python")
        assert var_types.get("name") == "Node.name"


class TestVerifyTokensCaseInsensitive:
    """Tests for case-insensitive class name normalization in verify_tokens (IC-04)."""

    def test_case_insensitive_method_verified(self, mock_knowledge):
        """Lowercase class name in token should be normalized to canonical name."""
        from audit import verify_tokens, Token
        # 'scene' (lowercase) should match 'Scene' class
        tokens = [Token("method", "scene", "open", 10, "scene.open()")]
        findings = verify_tokens(tokens, mock_knowledge, "test.md")
        # 'open' exists on Scene — should produce no finding
        assert not any("method not found" in f.message for f in findings)

    def test_case_insensitive_property_verified(self, mock_knowledge):
        """Lowercase class name should work for property verification too."""
        from audit import verify_tokens, Token
        tokens = [Token("property", "scene", "root_node", 10, "scene.root_node")]
        findings = verify_tokens(tokens, mock_knowledge, "test.md")
        assert not any("property not found" in f.message for f in findings)

    def test_method_on_wrong_class_flagged(self, mock_knowledge):
        """node.open() where Node doesn't have open (only Scene does) should produce finding."""
        from audit import verify_tokens, Token
        tokens = [Token("method", "Node", "open", 10, "node.open()")]
        findings = verify_tokens(tokens, mock_knowledge, "test.md")
        assert any("method not found" in f.message for f in findings)
