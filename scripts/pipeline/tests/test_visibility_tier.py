"""Tests for visibility_tier() and __all__ extraction in api_surface.py."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from extraction.tree_helpers import visibility_tier, get_parser, node_text, collect_nodes, _CLASS_TYPES


# ---------------------------------------------------------------------------
# visibility_tier() unit tests (language-specific logic)
# ---------------------------------------------------------------------------

class TestVisibilityTierPython:
    """Test Python visibility tier classification."""

    def test_in_module_all(self):
        node = MagicMock()
        assert visibility_tier(node, "python", has_docstring=True, in_module_all=True) == "exported"

    def test_has_docstring_no_all(self):
        node = MagicMock()
        assert visibility_tier(node, "python", has_docstring=True, in_module_all=False) == "public"

    def test_no_docstring_no_all(self):
        node = MagicMock()
        assert visibility_tier(node, "python", has_docstring=False, in_module_all=False) == "conventional"


class TestVisibilityTierOtherLanguages:

    def test_java_always_public(self):
        node = MagicMock()
        assert visibility_tier(node, "java") == "public"

    def test_csharp_always_public(self):
        node = MagicMock()
        assert visibility_tier(node, "csharp") == "public"

    def test_go_always_exported(self):
        node = MagicMock()
        assert visibility_tier(node, "go") == "exported"

    def test_typescript_export_statement(self):
        node = MagicMock()
        parent = MagicMock()
        parent.type = "export_statement"
        node.parent = parent
        assert visibility_tier(node, "typescript") == "exported"

    def test_typescript_no_export(self):
        node = MagicMock()
        parent = MagicMock()
        parent.type = "program"
        node.parent = parent
        assert visibility_tier(node, "typescript") == "public"


# ---------------------------------------------------------------------------
# Integration test: __all__ extraction + visibility in api_surface output
# ---------------------------------------------------------------------------

class TestPythonAllExtraction:
    """Test that __all__ names are extracted from Python modules."""

    @pytest.fixture
    def parser(self):
        return get_parser("python")

    def test_class_in_all_gets_exported(self, parser, tmp_path):
        """A class listed in __all__ should get visibility='exported'."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text(
            '__all__ = ["MyClass"]\n\n'
            'class MyClass:\n'
            '    """Documented class."""\n'
            '    def method(self): pass\n\n'
            'class Internal:\n'
            '    def method(self): pass\n'
        )

        from extraction.api_surface import extract_api_surface
        classes, _, _, _, _ = extract_api_surface(parser, "python", src, src, "test")

        by_name = {c["name"]: c for c in classes}
        assert "MyClass" in by_name
        assert by_name["MyClass"]["visibility"] == "exported"
        # Internal has no docstring and not in __all__
        if "Internal" in by_name:
            assert by_name["Internal"]["visibility"] == "conventional"

    def test_documented_class_gets_public(self, parser, tmp_path):
        """A class with a docstring but not in __all__ → 'public'."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text(
            'class DocClass:\n'
            '    """I have a docstring."""\n'
            '    def method(self): pass\n'
        )

        from extraction.api_surface import extract_api_surface
        classes, _, _, _, _ = extract_api_surface(parser, "python", src, src, "test")

        by_name = {c["name"]: c for c in classes}
        assert "DocClass" in by_name
        assert by_name["DocClass"]["visibility"] == "public"

    def test_undocumented_class_gets_conventional(self, parser, tmp_path):
        """A class without docstring and not in __all__ → 'conventional'."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text(
            'class Bare:\n'
            '    def method(self): pass\n'
        )

        from extraction.api_surface import extract_api_surface
        classes, _, _, _, _ = extract_api_surface(parser, "python", src, src, "test")

        by_name = {c["name"]: c for c in classes}
        assert "Bare" in by_name
        assert by_name["Bare"]["visibility"] == "conventional"

    def test_multi_entry_all_list(self, parser, tmp_path):
        """Multiple classes in __all__ should all get visibility='exported'."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text(
            '__all__ = ["Foo", "Bar", "Baz"]\n\n'
            'class Foo:\n'
            '    """Documented."""\n'
            '    def method(self): pass\n\n'
            'class Bar:\n'
            '    """Documented."""\n'
            '    def method(self): pass\n\n'
            'class Baz:\n'
            '    """Documented."""\n'
            '    def method(self): pass\n'
        )

        from extraction.api_surface import extract_api_surface
        classes, _, _, _, _ = extract_api_surface(parser, "python", src, src, "test")

        by_name = {c["name"]: c for c in classes}
        for name in ("Foo", "Bar", "Baz"):
            assert name in by_name, f"{name} not found in api_surface output"
            assert by_name[name]["visibility"] == "exported", \
                f"{name} should be exported but got {by_name[name]['visibility']}"

    def test_single_quoted_all_entries(self, parser, tmp_path):
        """__all__ with single-quoted strings should work identically."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text(
            "__all__ = ['OnlyClass']\n\n"
            'class OnlyClass:\n'
            '    """Has docstring."""\n'
            '    def method(self): pass\n'
        )

        from extraction.api_surface import extract_api_surface
        classes, _, _, _, _ = extract_api_surface(parser, "python", src, src, "test")

        by_name = {c["name"]: c for c in classes}
        assert "OnlyClass" in by_name
        assert by_name["OnlyClass"]["visibility"] == "exported"

    def test_class_not_in_all_with_docstring_gets_public(self, parser, tmp_path):
        """Class with docstring but NOT in __all__ → 'public' (not exported)."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text(
            '__all__ = ["Exported"]\n\n'
            'class Exported:\n'
            '    """In __all__."""\n'
            '    def method(self): pass\n\n'
            'class NotExported:\n'
            '    """Has docstring but not in __all__."""\n'
            '    def method(self): pass\n'
        )

        from extraction.api_surface import extract_api_surface
        classes, _, _, _, _ = extract_api_surface(parser, "python", src, src, "test")

        by_name = {c["name"]: c for c in classes}
        assert by_name["Exported"]["visibility"] == "exported"
        assert by_name["NotExported"]["visibility"] == "public"
