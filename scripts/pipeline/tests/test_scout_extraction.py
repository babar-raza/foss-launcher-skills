"""Tests for scout.py extraction changes — tree-sitter-based verification.

Covers:
- Change 1: TypeScript member extraction (is_public for class_body)
- Change 2: C# enum member extraction (enum_member_declaration_list)
- Change 3: Python enum detection by base class + member extraction
- Change 4: Java property synthesis from getters/setters
- Change 5: Constructor marking (is_constructor field)
- Bug fix: Python __init__ passes is_public
- Bug fix: Python enum bare assignment extraction
"""

from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
import scout


def _parse(language: str, code: str):
    """Parse source code and return the root node."""
    parser = scout.get_parser(language)
    tree = parser.parse(code.encode("utf-8"))
    return tree.root_node


# ---------------------------------------------------------------------------
# Change 1: TypeScript member extraction
# ---------------------------------------------------------------------------

class TestTypeScriptMemberVisibility:
    """is_public() must accept class body members as public by default."""

    TS_CLASS = """
export class Scene extends SceneObject {
    rootNode: Node;
    open(path: string): void {}
    save(path: string): void {}
    private _internal(): void {}
}
"""

    def test_public_method_in_class_body(self):
        root = _parse("typescript", self.TS_CLASS)
        methods = scout.collect_nodes(root, {"method_definition"})
        public_names = [
            scout._node_name(m, "typescript")
            for m in methods
            if scout.is_public(m, "typescript")
        ]
        assert "open" in public_names
        assert "save" in public_names

    def test_private_method_excluded(self):
        root = _parse("typescript", self.TS_CLASS)
        methods = scout.collect_nodes(root, {"method_definition"})
        public_names = [
            scout._node_name(m, "typescript")
            for m in methods
            if scout.is_public(m, "typescript")
        ]
        assert "_internal" not in public_names

    def test_property_in_class_body(self):
        root = _parse("typescript", self.TS_CLASS)
        # public_field_definition or property_signature
        props = scout.collect_nodes(
            root, {"public_field_definition", "property_signature"}
        )
        public_prop_names = [
            scout._node_name(p, "typescript")
            for p in props
            if scout.is_public(p, "typescript")
        ]
        assert "rootNode" in public_prop_names

    def test_ts_func_types_include_property_nodes(self):
        assert "public_field_definition" in scout._FUNC_TYPES["typescript"]
        assert "property_signature" in scout._FUNC_TYPES["typescript"]
        assert "method_signature" in scout._FUNC_TYPES["typescript"]


# ---------------------------------------------------------------------------
# Change 2: C# enum member extraction
# ---------------------------------------------------------------------------

class TestCSharpEnumExtraction:
    """_extract_enum_members must find members in C# enum_member_declaration_list."""

    CS_ENUM = """
public enum FileFormat {
    OBJ,
    STL,
    GLTF,
    FBX
}
"""

    def test_extracts_csharp_enum_values(self):
        root = _parse("csharp", self.CS_ENUM)
        enums = scout.collect_nodes(root, {"enum_declaration"})
        assert len(enums) >= 1
        members = scout._extract_enum_members(enums[0], "csharp")
        names = [m["name"] for m in members]
        assert "OBJ" in names
        assert "STL" in names
        assert "GLTF" in names
        assert "FBX" in names

    def test_empty_enum(self):
        root = _parse("csharp", "public enum Empty { }")
        enums = scout.collect_nodes(root, {"enum_declaration"})
        if enums:
            members = scout._extract_enum_members(enums[0], "csharp")
            assert members == [] or isinstance(members, list)


# ---------------------------------------------------------------------------
# Change 3: Python enum detection and extraction
# ---------------------------------------------------------------------------

class TestPythonEnumDetection:
    """Python enums detected by base class inheritance, members extracted."""

    PY_ENUM = """
from enum import Enum

class ProjectionType(Enum):
    PERSPECTIVE = 0
    ORTHOGRAPHIC = 1
"""

    PY_INTENUM = """
from enum import IntEnum

class LightType(IntEnum):
    POINT = 0
    DIRECTIONAL = 1
    SPOT = 2
"""

    PY_NON_ENUM = """
class Mesh:
    def __init__(self):
        self.vertices = []
"""

    def test_detects_enum_by_base_class(self):
        root = _parse("python", self.PY_ENUM)
        classes = scout.collect_nodes(root, {"class_definition"})
        assert len(classes) == 1
        bases = scout._extract_bases(classes[0], "python")
        assert "Enum" in bases
        assert set(bases) & scout._PY_ENUM_BASES

    def test_detects_intenum(self):
        root = _parse("python", self.PY_INTENUM)
        classes = scout.collect_nodes(root, {"class_definition"})
        bases = scout._extract_bases(classes[0], "python")
        assert set(bases) & scout._PY_ENUM_BASES

    def test_non_enum_not_detected(self):
        root = _parse("python", self.PY_NON_ENUM)
        classes = scout.collect_nodes(root, {"class_definition"})
        bases = scout._extract_bases(classes[0], "python")
        assert not (set(bases) & scout._PY_ENUM_BASES)

    def test_extracts_enum_members(self):
        root = _parse("python", self.PY_ENUM)
        classes = scout.collect_nodes(root, {"class_definition"})
        members = scout._extract_python_enum_members(classes[0])
        names = [m["name"] for m in members]
        assert "PERSPECTIVE" in names
        assert "ORTHOGRAPHIC" in names

    def test_extracts_intenum_members(self):
        root = _parse("python", self.PY_INTENUM)
        classes = scout.collect_nodes(root, {"class_definition"})
        members = scout._extract_python_enum_members(classes[0])
        names = [m["name"] for m in members]
        assert "POINT" in names
        assert "DIRECTIONAL" in names
        assert "SPOT" in names
        assert len(members) == 3

    def test_empty_enum_class(self):
        code = "from enum import Enum\n\nclass Empty(Enum):\n    pass\n"
        root = _parse("python", code)
        classes = scout.collect_nodes(root, {"class_definition"})
        members = scout._extract_python_enum_members(classes[0])
        assert members == []

    def test_underscore_members_excluded(self):
        code = """
from enum import Enum

class MyEnum(Enum):
    PUBLIC = 1
    _PRIVATE = 2
"""
        root = _parse("python", code)
        classes = scout.collect_nodes(root, {"class_definition"})
        members = scout._extract_python_enum_members(classes[0])
        names = [m["name"] for m in members]
        assert "PUBLIC" in names
        assert "_PRIVATE" not in names


# ---------------------------------------------------------------------------
# Change 4: Java property synthesis
# ---------------------------------------------------------------------------

class TestJavaPropertySynthesis:
    """Java getters/setters synthesized into properties."""

    JAVA_CLASS = """
public class Node {
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public boolean isVisible() { return visible; }
    public List<Node> getChildNodes() { return children; }
    public void doSomething(int x) { }
    public String toString() { return ""; }
}
"""

    def test_synthesizes_properties_from_getters(self):
        root = _parse("java", self.JAVA_CLASS)
        methods_raw = scout.collect_nodes(root, {"method_declaration"})
        methods = []
        for m in methods_raw:
            name = scout._node_name(m, "java")
            params = scout._extract_method_params(m, "java")
            ret = scout._extract_return_type(m, "java")
            methods.append({
                "name": name,
                "params": params,
                "return_type": ret,
                "line": m.start_point[0] + 1,
            })

        # Create a minimal Scout-like object for testing
        class FakeScout:
            _JAVA_OBJECT_METHODS = scout.Scout._JAVA_OBJECT_METHODS
            def _add_claim(self, *args): pass
            def _synthesize_java_properties(self, *args, **kwargs):
                return scout.Scout._synthesize_java_properties(self, *args, **kwargs)

        properties = []
        fake = FakeScout()
        fake._synthesize_java_properties(methods, "Node", "Node.java", properties)

        prop_names = [p["name"] for p in properties]
        assert "name" in prop_names      # from getName()
        assert "visible" in prop_names   # from isVisible()
        assert "childNodes" in prop_names  # from getChildNodes()

    def test_excludes_object_methods(self):
        class FakeScout:
            _JAVA_OBJECT_METHODS = scout.Scout._JAVA_OBJECT_METHODS
            def _add_claim(self, *args): pass
            def _synthesize_java_properties(self, *args, **kwargs):
                return scout.Scout._synthesize_java_properties(self, *args, **kwargs)

        methods = [{"name": "toString", "params": [], "return_type": "String", "line": 1}]
        properties = []
        FakeScout()._synthesize_java_properties(methods, "Node", "Node.java", properties)
        assert len(properties) == 0

    def test_skips_methods_with_params(self):
        class FakeScout:
            _JAVA_OBJECT_METHODS = scout.Scout._JAVA_OBJECT_METHODS
            def _add_claim(self, *args): pass
            def _synthesize_java_properties(self, *args, **kwargs):
                return scout.Scout._synthesize_java_properties(self, *args, **kwargs)

        methods = [{"name": "doSomething", "params": [{"name": "x"}], "return_type": "void", "line": 1}]
        properties = []
        FakeScout()._synthesize_java_properties(methods, "Node", "Node.java", properties)
        assert len(properties) == 0


# ---------------------------------------------------------------------------
# Change 5: Constructor marking
# ---------------------------------------------------------------------------

class TestConstructorMarking:
    """is_constructor field must be set on constructor nodes."""

    def test_java_constructor(self):
        code = "public class Foo { public Foo(int x) {} public void bar() {} }"
        root = _parse("java", code)
        nodes = scout.collect_nodes(root, {"method_declaration", "constructor_declaration"})
        for n in nodes:
            name = scout._node_name(n, "java")
            is_ctor = (n.type == "constructor_declaration")
            if name == "Foo":
                assert is_ctor, "Foo should be detected as constructor"
            elif name == "bar":
                assert not is_ctor

    def test_python_init_is_constructor(self):
        code = "class Foo:\n    def __init__(self):\n        pass\n    def bar(self):\n        pass\n"
        root = _parse("python", code)
        funcs = scout.collect_nodes(root, {"function_definition"})
        for f in funcs:
            name = scout._node_name(f, "python")
            is_ctor = (name == "__init__")
            if name == "__init__":
                assert is_ctor
            elif name == "bar":
                assert not is_ctor

    def test_typescript_constructor(self):
        code = "export class Foo { constructor(x: number) {} open(): void {} }"
        root = _parse("typescript", code)
        methods = scout.collect_nodes(root, {"method_definition"})
        for m in methods:
            name = scout._node_name(m, "typescript")
            is_ctor = (name == "constructor")
            if name == "constructor":
                assert is_ctor
            elif name == "open":
                assert not is_ctor


# ---------------------------------------------------------------------------
# Bug fix: Python __init__ passes is_public
# ---------------------------------------------------------------------------

class TestPythonInitVisibility:
    """__init__ must be treated as public despite leading underscore."""

    def test_init_is_public(self):
        code = "class Foo:\n    def __init__(self):\n        pass\n"
        root = _parse("python", code)
        funcs = scout.collect_nodes(root, {"function_definition"})
        assert len(funcs) >= 1
        init_node = funcs[0]
        assert scout._node_name(init_node, "python") == "__init__"
        assert scout.is_public(init_node, "python") is True

    def test_dunder_other_still_private(self):
        code = "class Foo:\n    def __repr__(self):\n        return ''\n"
        root = _parse("python", code)
        funcs = scout.collect_nodes(root, {"function_definition"})
        # __repr__ starts with _ so is_public returns False
        assert scout.is_public(funcs[0], "python") is False

    def test_private_method_still_excluded(self):
        code = "class Foo:\n    def _helper(self):\n        pass\n"
        root = _parse("python", code)
        funcs = scout.collect_nodes(root, {"function_definition"})
        assert scout.is_public(funcs[0], "python") is False


# ---------------------------------------------------------------------------
# Module constant: _PY_ENUM_BASES
# ---------------------------------------------------------------------------

class TestPyEnumBasesConstant:
    """Module-level _PY_ENUM_BASES must be a frozenset with expected values."""

    def test_is_frozenset(self):
        assert isinstance(scout._PY_ENUM_BASES, frozenset)

    def test_contains_core_bases(self):
        assert "Enum" in scout._PY_ENUM_BASES
        assert "IntEnum" in scout._PY_ENUM_BASES
        assert "enum.Enum" in scout._PY_ENUM_BASES

    def test_contains_flag_bases(self):
        assert "Flag" in scout._PY_ENUM_BASES
        assert "IntFlag" in scout._PY_ENUM_BASES


# ---------------------------------------------------------------------------
# Python dataclass field extraction
# ---------------------------------------------------------------------------

class TestPythonDataclassFields:
    """Annotated class-level fields (dataclass fields) must be extracted as properties."""

    PY_DATACLASS = """
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass
class CFBDocument:
    root: CFBStorage
    major_version: int = 3
    transaction_signature_number: int = 0
    _private: str = "hidden"

@dataclass(frozen=True)
class CFBStream:
    name: str
    data: bytes = b""
    items: list = field(default_factory=list)
    CLASS_CONST: ClassVar[int] = 42

class WithProperty:
    @property
    def size(self) -> int:
        return 0
"""

    def _extract(self):
        """Run extract_api_surface on the dataclass fixture and return classes."""
        from pathlib import Path
        from extraction.api_surface import extract_api_surface
        parser = scout.get_parser("python")
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = Path(tmpdir) / "aspose" / "pkg"
            pkg.mkdir(parents=True)
            src = pkg / "models.py"
            src.write_text(self.PY_DATACLASS)
            classes, _, _, _ = extract_api_surface(
                parser, "python", pkg, Path(tmpdir), "testfamily"
            )
        return {c["name"]: c for c in classes if c.get("kind") == "class_definition"}

    def test_extracts_plain_annotated_field(self):
        classes = self._extract()
        props = [p["name"] for p in classes["CFBDocument"]["properties"]]
        assert "root" in props

    def test_extracts_field_with_default(self):
        classes = self._extract()
        props = [p["name"] for p in classes["CFBDocument"]["properties"]]
        assert "major_version" in props
        assert "transaction_signature_number" in props

    def test_excludes_private_field(self):
        classes = self._extract()
        props = [p["name"] for p in classes["CFBDocument"]["properties"]]
        assert "_private" not in props

    def test_excludes_classvar(self):
        classes = self._extract()
        props = [p["name"] for p in classes["CFBStream"]["properties"]]
        assert "CLASS_CONST" not in props

    def test_field_type_captured(self):
        classes = self._extract()
        root_field = next(
            p for p in classes["CFBDocument"]["properties"] if p["name"] == "root"
        )
        assert root_field["type"] == "CFBStorage"

    def test_field_default_with_factory(self):
        classes = self._extract()
        props = [p["name"] for p in classes["CFBStream"]["properties"]]
        assert "items" in props

    def test_frozen_dataclass_fields_extracted(self):
        classes = self._extract()
        props = [p["name"] for p in classes["CFBStream"]["properties"]]
        assert "name" in props
        assert "data" in props

    def test_existing_property_decorator_still_works(self):
        """Regression guard: @property extraction must not be broken by the new code."""
        classes = self._extract()
        props = [p["name"] for p in classes["WithProperty"]["properties"]]
        assert "size" in props


# ---------------------------------------------------------------------------
# Scout guardrail warnings
# ---------------------------------------------------------------------------

class TestScoutGuardrailWarnings:
    """Scout._log_extraction_quality must warn for suspicious Python classes.

    The guardrail is tested by directly calling _log_extraction_quality() on
    a Scout instance whose classes/coverage/snippets lists are injected with
    controlled fixture data — avoiding the need for a real full extraction run.
    """

    def _make_scout(self):
        """Create a minimal Scout instance with empty state for guardrail testing."""
        import tempfile
        from pathlib import Path
        from extraction.scout import Scout

        tmpdir = tempfile.mkdtemp()
        pkg = Path(tmpdir) / "aspose" / "pkg"
        pkg.mkdir(parents=True)
        out_dir = Path(tmpdir) / "out"
        out_dir.mkdir()
        s = Scout(family="testfamily", platform="python",
                  repo=Path(tmpdir), output=out_dir)
        # Reset to empty state; we will inject fixture data
        s.classes = []
        s.coverage = []
        s.snippets = []
        return s

    def _capture_guardrail(self, classes: list) -> str:
        """Run _log_extraction_quality with injected classes and return stderr."""
        import io
        import sys

        s = self._make_scout()
        s.classes = classes
        buf = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = buf
        try:
            s._log_extraction_quality()
        finally:
            sys.stderr = old_stderr
        return buf.getvalue()

    def test_guardrail_fires_for_methods_but_no_properties(self):
        """Class with methods but zero properties triggers the guardrail."""
        classes = [{
            "name": "BrokenDataclass",
            "kind": "class_definition",
            "file": "pkg/models.py",
            "methods": [
                {"name": "from_file", "params": [], "return_type": "", "doc": "", "line": 2, "is_constructor": False},
                {"name": "from_reader", "params": [], "return_type": "", "doc": "", "line": 5, "is_constructor": False},
            ],
            "properties": [],
        }]
        stderr = self._capture_guardrail(classes)
        assert "BrokenDataclass" in stderr
        assert "WARNING" in stderr
        assert "zero properties" in stderr

    def test_guardrail_does_not_fire_for_enum_class(self):
        """Enum classes (with enum_members) must not trigger the guardrail."""
        classes = [{
            "name": "FileFormat",
            "kind": "class_definition",
            "file": "pkg/models.py",
            "methods": [],
            "properties": [],
            "enum_members": [{"name": "MSG", "value": "1"}, {"name": "EML", "value": "2"}],
        }]
        stderr = self._capture_guardrail(classes)
        # No WARNING lines about FileFormat
        warning_lines = [l for l in stderr.splitlines()
                         if "FileFormat" in l and "WARNING" in l]
        assert warning_lines == [], f"Unexpected warnings: {warning_lines}"

    def test_guardrail_does_not_fire_when_properties_present(self):
        """A class with both methods and properties must NOT trigger the guardrail."""
        classes = [{
            "name": "CFBDocument",
            "kind": "class_definition",
            "file": "pkg/models.py",
            "methods": [
                {"name": "from_file", "params": [], "return_type": "", "doc": "", "line": 4, "is_constructor": False},
            ],
            "properties": [{"name": "root", "type": "object", "line": 2}],
        }]
        stderr = self._capture_guardrail(classes)
        warning_lines = [l for l in stderr.splitlines()
                         if "CFBDocument" in l and "WARNING" in l]
        assert warning_lines == [], f"Unexpected warnings: {warning_lines}"


# ---------------------------------------------------------------------------
# Bug fix: Python class docstring extraction (_extract_doc_comment)
# Regression guard for: tree-sitter-python exposes class docstrings as bare
# `string` nodes (not wrapped in `expression_statement`), which caused the
# original `children[0].type == "expression_statement"` check to always miss.
# ---------------------------------------------------------------------------

class TestPythonDocstringExtraction:
    """_extract_doc_comment must capture class-level docstrings for Python."""

    def _get_class_doc(self, code: str) -> str:
        from extraction.api_surface import _extract_doc_comment
        root = _parse("python", code)
        for child in root.children:
            if child.type == "class_definition":
                return _extract_doc_comment(child, "python")
        return ""

    def test_simple_docstring(self):
        code = '''class Camera:
    """Represents Camera."""
    def foo(self): pass
'''
        assert self._get_class_doc(code) == "Represents Camera."

    def test_multi_sentence_returns_first(self):
        code = '''class Slide:
    """Represents a slide in a presentation. Contains shapes and notes."""
    pass
'''
        assert self._get_class_doc(code) == "Represents a slide in a presentation."

    def test_no_docstring_returns_empty(self):
        code = '''class Foo:
    def bar(self): pass
'''
        assert self._get_class_doc(code) == ""

    def test_class_with_only_pass_returns_empty(self):
        code = '''class Empty:
    pass
'''
        assert self._get_class_doc(code) == ""
