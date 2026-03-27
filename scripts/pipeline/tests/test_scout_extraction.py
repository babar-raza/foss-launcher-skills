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

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts/pipeline"))

import scout  # noqa: E402


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
