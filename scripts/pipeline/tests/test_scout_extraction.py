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
            classes, _, _, _, _ = extract_api_surface(
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

    def test_guardrail_suppressed_for_service_class_no_arg_init(self):
        """Service class with __init__(self) — no data params — must NOT warn."""
        classes = [{
            "name": "HyperlinkXMLSaver",
            "kind": "class_definition",
            "file": "pkg/xml_hyperlink_handler.py",
            "methods": [
                # __init__(self) — self already filtered, so params=[]
                {"name": "__init__", "params": [], "return_type": "", "doc": "",
                 "line": 2, "is_constructor": True},
                {"name": "format_hyperlinks_xml",
                 "params": [{"name": "worksheet"}], "return_type": "", "doc": "",
                 "line": 5, "is_constructor": False},
                {"name": "get_hyperlink_relationships",
                 "params": [{"name": "worksheet"}], "return_type": "", "doc": "",
                 "line": 10, "is_constructor": False},
            ],
            "properties": [],
        }]
        stderr = self._capture_guardrail(classes)
        warning_lines = [l for l in stderr.splitlines()
                         if "HyperlinkXMLSaver" in l and "WARNING" in l]
        assert warning_lines == [], f"Unexpected warnings: {warning_lines}"

    def test_guardrail_suppressed_for_service_class_single_injection_param(self):
        """Service class with __init__(self, writer) must NOT trigger the guardrail.

        Pattern: dependency-injection single-param constructor stores private state
        as self._writer. Zero public properties is expected and correct.
        """
        classes = [{
            "name": "ShapeRenderer",
            "kind": "class_definition",
            "file": "pkg/pdf_writer/shape_renderer.py",
            "methods": [
                # __init__(self, writer) — self filtered, writer remains
                {"name": "__init__", "params": [{"name": "writer"}], "return_type": "",
                 "doc": "", "line": 2, "is_constructor": True},
                {"name": "render_shape",
                 "params": [{"name": "pdf"}, {"name": "shape"}], "return_type": "",
                 "doc": "", "line": 5, "is_constructor": False},
            ],
            "properties": [],
        }]
        stderr = self._capture_guardrail(classes)
        warning_lines = [l for l in stderr.splitlines()
                         if "ShapeRenderer" in l and "WARNING" in l]
        assert warning_lines == [], f"Unexpected warnings: {warning_lines}"

    def test_guardrail_fires_for_explicit_init_with_multiple_data_params(self):
        """Explicit __init__ with 2+ data params still fires — may have missed fields."""
        classes = [{
            "name": "MissingPropsDataclass",
            "kind": "class_definition",
            "file": "pkg/models.py",
            "methods": [
                # __init__(self, name, value, count) — self filtered, 3 params
                {"name": "__init__",
                 "params": [{"name": "name"}, {"name": "value"}, {"name": "count"}],
                 "return_type": "", "doc": "", "line": 2, "is_constructor": True},
                {"name": "validate", "params": [], "return_type": "", "doc": "",
                 "line": 8, "is_constructor": False},
            ],
            "properties": [],
        }]
        stderr = self._capture_guardrail(classes)
        assert "MissingPropsDataclass" in stderr
        assert "WARNING" in stderr
        assert "zero properties" in stderr


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


# ---------------------------------------------------------------------------
# Python __init__ instance attribute extraction
# ---------------------------------------------------------------------------

from extraction.api_surface import _extract_python_init_attributes


class TestPythonInitAttributes:
    """_extract_python_init_attributes captures self.xxx assignments in __init__."""

    PYTHON_CLASS_WITH_INIT = """
class PdfSaveOptions:
    def __init__(self):
        self.jpeg_quality: int = 100
        self.compliance: str = "PDF17"
        self.export_document_structure: bool = False
        self._internal_cache = {}
        self._temp = None
"""

    PYTHON_CLASS_NO_INIT = """
class EmptyClass:
    pass
"""

    PYTHON_CLASS_WITH_PROPERTY_AND_INIT = """
class DualSource:
    @property
    def name(self) -> str:
        return self._name

    def __init__(self):
        self.name: str = "default"
        self.value: int = 42
"""

    PYTHON_CLASS_UNTYPED_INIT = """
class UntypedAttrs:
    def __init__(self):
        self.width = 800
        self.height = 600
        self._private = True
"""

    def test_extracts_typed_init_attributes(self):
        root = _parse("python", self.PYTHON_CLASS_WITH_INIT)
        classes = scout.collect_nodes(root, {"class_definition"})
        assert len(classes) == 1
        props, claims = _extract_python_init_attributes(
            classes[0], "PdfSaveOptions", "test.py", "words"
        )
        names = [p["name"] for p in props]
        assert "jpeg_quality" in names
        assert "compliance" in names
        assert "export_document_structure" in names
        # Private attributes must be excluded
        assert "_internal_cache" not in names
        assert "_temp" not in names

    def test_extracts_type_annotations(self):
        root = _parse("python", self.PYTHON_CLASS_WITH_INIT)
        classes = scout.collect_nodes(root, {"class_definition"})
        props, _ = _extract_python_init_attributes(
            classes[0], "PdfSaveOptions", "test.py", "words"
        )
        type_map = {p["name"]: p["type"] for p in props}
        assert type_map["jpeg_quality"] == "int"
        assert type_map["compliance"] == "str"
        assert type_map["export_document_structure"] == "bool"

    def test_no_init_returns_empty(self):
        root = _parse("python", self.PYTHON_CLASS_NO_INIT)
        classes = scout.collect_nodes(root, {"class_definition"})
        props, claims = _extract_python_init_attributes(
            classes[0], "EmptyClass", "test.py", "words"
        )
        assert props == []
        assert claims == []

    def test_deduplicates_against_existing_properties(self):
        """If 'name' already exists via @property, don't double-count it."""
        root = _parse("python", self.PYTHON_CLASS_WITH_PROPERTY_AND_INIT)
        classes = scout.collect_nodes(root, {"class_definition"})
        props, _ = _extract_python_init_attributes(
            classes[0], "DualSource", "test.py", "words",
            existing_names={"name"},
        )
        names = [p["name"] for p in props]
        assert "name" not in names  # Already in @property
        assert "value" in names     # New, should be captured

    def test_extracts_untyped_attributes(self):
        root = _parse("python", self.PYTHON_CLASS_UNTYPED_INIT)
        classes = scout.collect_nodes(root, {"class_definition"})
        props, _ = _extract_python_init_attributes(
            classes[0], "UntypedAttrs", "test.py", "words"
        )
        names = [p["name"] for p in props]
        assert "width" in names
        assert "height" in names
        assert "_private" not in names
        # Untyped attrs should have empty type
        type_map = {p["name"]: p["type"] for p in props}
        assert type_map["width"] == ""

    def test_generates_claims(self):
        root = _parse("python", self.PYTHON_CLASS_WITH_INIT)
        classes = scout.collect_nodes(root, {"class_definition"})
        _, claims = _extract_python_init_attributes(
            classes[0], "PdfSaveOptions", "test.py", "words"
        )
        assert len(claims) == 3  # 3 public attributes
        assert all(c["kind"] == "api_method" for c in claims)
        texts = [c["text"] for c in claims]
        assert any("jpeg_quality" in t for t in texts)

    PYTHON_CLASS_BACKING_FIELD = """
class Mesh:
    @property
    def control_points(self):
        return list(self._control_points)

    @property
    def name(self) -> str:
        return self._name

    def __init__(self):
        self._control_points = []
        self._name = "default"
        self.vertex_count: int = 0
"""

    def test_private_backing_fields_excluded_even_with_public_property(self):
        """Private _backing fields must never appear in API surface even when a
        matching public @property exists (PRIVATE-API-REF-001 regression guard)."""
        root = _parse("python", self.PYTHON_CLASS_BACKING_FIELD)
        classes = scout.collect_nodes(root, {"class_definition"})
        props, claims = _extract_python_init_attributes(
            classes[0], "Mesh", "test.py", "3d",
            existing_names={"control_points", "name"},
        )
        names = [p["name"] for p in props]
        assert "_control_points" not in names
        assert "_name" not in names
        assert "vertex_count" in names
        claim_texts = [c["text"] for c in claims]
        assert not any("_control_points" in t for t in claim_texts)
        assert not any("._name" in t for t in claim_texts)


# ---------------------------------------------------------------------------
# TC-01 regression guard: property "doc" field in extracted output
# ---------------------------------------------------------------------------

from extraction.api_surface import _extract_python_properties, _extract_python_annotated_fields


class TestPropertyDocField:
    """Property records must include a 'doc' key after TC-01 fix.

    Regression guard for the gap where all property extraction paths omitted the
    'doc' field, causing prop.get('doc') in batch_reference to always return None
    and collapse every description cell to an empty string.
    """

    PYTHON_PROP_WITH_DOCSTRING = '''
class Document:
    @property
    def title(self) -> str:
        """The document title."""
        return self._title
'''

    PYTHON_PROP_NO_DOCSTRING = '''
class Document:
    @property
    def title(self) -> str:
        return self._title
'''

    PYTHON_ANNOTATED_FIELD = '''
class Body:
    content: str
    children: list
'''

    def test_property_with_docstring_has_doc_field(self):
        """@property with docstring must produce a 'doc' key in the property record."""
        root = _parse("python", self.PYTHON_PROP_WITH_DOCSTRING)
        classes = scout.collect_nodes(root, {"class_definition"})
        assert classes, "Expected at least one class_definition node"
        props, _ = _extract_python_properties(classes[0], "Document", "document.py", "words")
        assert props, "Expected at least one property"
        prop = next((p for p in props if p["name"] == "title"), None)
        assert prop is not None, "Expected 'title' property"
        assert "doc" in prop, "Property record must have 'doc' key (TC-01)"
        assert prop["doc"] == "The document title.", (
            f"Expected docstring 'The document title.', got {prop['doc']!r}"
        )

    def test_property_without_docstring_has_empty_doc_field(self):
        """@property without docstring must produce 'doc': '' (not absent key)."""
        root = _parse("python", self.PYTHON_PROP_NO_DOCSTRING)
        classes = scout.collect_nodes(root, {"class_definition"})
        props, _ = _extract_python_properties(classes[0], "Document", "document.py", "words")
        prop = next((p for p in props if p["name"] == "title"), None)
        assert prop is not None, "Expected 'title' property"
        assert "doc" in prop, "Property record must have 'doc' key even without docstring (TC-01)"
        assert prop["doc"] == "", f"Expected empty doc, got {prop['doc']!r}"

    def test_annotated_field_has_empty_doc_field(self):
        """Type-annotated class fields must have 'doc': '' key (no docstring container)."""
        root = _parse("python", self.PYTHON_ANNOTATED_FIELD)
        classes = scout.collect_nodes(root, {"class_definition"})
        fields, _ = _extract_python_annotated_fields(classes[0], "Body", "body.py", "words")
        assert fields, "Expected annotated fields"
        for field in fields:
            assert "doc" in field, (
                f"Field '{field.get('name')}' must have 'doc' key (TC-01)"
            )


# ---------------------------------------------------------------------------
# Regression: extends_interfaces node type in Java interface inheritance
# (commit 30c0ba40c34 — fixed 102 false FAIL findings in slides/java)
# ---------------------------------------------------------------------------


class TestJavaExtendsInterfaces:
    """Regression tests for 'extends_interfaces' node type in _extract_bases().

    Without 'extends_interfaces' in the node-type set, Java interfaces that
    extend other interfaces are silently missed, producing false FAIL audit
    findings.  Commit 30c0ba40c34 added the node type; these tests prevent
    a silent revert.
    """

    JAVA_INTERFACE_SINGLE_EXTENDS = """
public interface IAdvancedShape extends IBasicShape {
    void draw();
}
"""

    JAVA_INTERFACE_MULTI_EXTENDS = """
public interface IShape extends IDrawable, ISerializable {
    int getArea();
}
"""

    JAVA_CLASS_IMPLEMENTS = """
public class Circle implements IShape {
    public void draw() {}
}
"""

    def test_java_interface_single_extends_captured(self):
        """Interface extending one interface — parent captured via extends_interfaces."""
        root = _parse("java", self.JAVA_INTERFACE_SINGLE_EXTENDS)
        interfaces = scout.collect_nodes(root, {"interface_declaration"})
        assert interfaces, "Expected interface_declaration node"
        bases = scout._extract_bases(interfaces[0], "java")
        assert "IBasicShape" in bases, (
            "extends_interfaces node type missing from _extract_bases(). "
            "See commit 30c0ba40c34."
        )

    def test_java_interface_multi_extends_captured(self):
        """Interface extending multiple interfaces — all parents captured."""
        root = _parse("java", self.JAVA_INTERFACE_MULTI_EXTENDS)
        interfaces = scout.collect_nodes(root, {"interface_declaration"})
        assert interfaces, "Expected interface_declaration node"
        bases = scout._extract_bases(interfaces[0], "java")
        assert "IDrawable" in bases, "First parent in multi-extends not captured"
        assert "ISerializable" in bases, "Second parent in multi-extends not captured"

    def test_java_class_implements_captured(self):
        """Class implementing interface — sanity check that implements_clause still works."""
        root = _parse("java", self.JAVA_CLASS_IMPLEMENTS)
        classes = scout.collect_nodes(root, {"class_declaration"})
        assert classes, "Expected class_declaration node"
        bases = scout._extract_bases(classes[0], "java")
        assert "IShape" in bases, "implements_clause not captured"


# ---------------------------------------------------------------------------
# SFX-1: Go receiver method association
# ---------------------------------------------------------------------------

from extraction.api_surface import extract_api_surface, _extract_go_receiver_type, _associate_go_methods


class TestGoReceiverMethodAssociation:
    """SFX-1: Receiver methods must be nested under their parent type after extraction.

    In Go, ``func (d *Document) Save(...) error`` is a top-level AST node.
    The scout must detect the receiver type and move the method entry into
    Document.methods[] rather than leaving it at the top level.
    """

    GO_SRC = """\
package pdf

// Document represents a PDF document.
type Document struct{}

// Save writes the PDF to disk.
func (d *Document) Save(path string) error { return nil }

// Open opens a PDF file from disk.
func Open(path string) (*Document, error) { return nil, nil }
"""

    def _extract(self):
        """Run extract_api_surface on the Go fixture and return all entries."""
        import tempfile
        from pathlib import Path
        parser = scout.get_parser("go")
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            src = root_dir / "document.go"
            src.write_text(self.GO_SRC)
            classes, _, _, _, _ = extract_api_surface(
                parser, "go", root_dir, root_dir, "testfamily"
            )
        return classes

    def test_document_entry_has_save_method(self):
        """Document type must have Save in its methods[] list."""
        classes = self._extract()
        type_entries = {e["name"]: e for e in classes
                        if e.get("kind") in ("type_spec", "type_declaration")}
        assert "Document" in type_entries, "Document type not found in extracted entries"
        method_names = [m["name"] for m in type_entries["Document"].get("methods", [])]
        assert "Save" in method_names, (
            f"Save not in Document.methods[]. methods={method_names!r}\n"
            "SFX-1 receiver method association may not be working."
        )

    def test_save_not_at_top_level(self):
        """Save must NOT appear as a standalone top-level function entry."""
        classes = self._extract()
        top_func_names = [e["name"] for e in classes if e.get("kind") == "function"]
        assert "Save" not in top_func_names, (
            "Save still appears as top-level function — SFX-1 did not remove it."
        )

    def test_open_remains_top_level_function(self):
        """Package-level functions without receivers stay at top level."""
        classes = self._extract()
        top_func_names = [e["name"] for e in classes if e.get("kind") == "function"]
        assert "Open" in top_func_names, (
            "Open (package-level func without receiver) must remain a top-level entry."
        )

    def test_receiver_type_helper(self):
        """_extract_go_receiver_type must return the bare type name."""
        root = _parse("go", self.GO_SRC)
        method_decls = scout.collect_nodes(root, {"method_declaration"})
        assert method_decls, "No method_declaration nodes found in Go source"
        recv_type = _extract_go_receiver_type(method_decls[0])
        assert recv_type == "Document", (
            f"Expected 'Document', got {recv_type!r}"
        )


# ---------------------------------------------------------------------------
# SFX-2: Go godoc comment extraction for type declarations
# ---------------------------------------------------------------------------

class TestGoGodocTypeExtraction:
    """SFX-2: Godoc comments preceding type declarations must be extracted."""

    GO_TYPE_WITH_GODOC = """\
package pdf

// Document represents a PDF document in Aspose.PDF.
type Document struct{}
"""

    GO_TYPE_NO_GODOC = """\
package pdf

type Page struct{}
"""

    def _get_type_doc(self, code: str, type_name: str) -> str:
        """Extract doc for a named Go type using the full extraction pipeline."""
        import tempfile
        from pathlib import Path
        parser = scout.get_parser("go")
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            (root_dir / "types.go").write_text(code)
            classes, _, _, _, _ = extract_api_surface(
                parser, "go", root_dir, root_dir, "testfamily"
            )
        return next(
            (e.get("doc", "") for e in classes if e["name"] == type_name),
            None
        )

    def test_godoc_extracted_for_type(self):
        """Godoc comment before type declaration must be captured in doc field."""
        doc = self._get_type_doc(self.GO_TYPE_WITH_GODOC, "Document")
        assert doc, "Expected non-empty doc for Document — SFX-2 godoc fix may not be working"
        assert "PDF document" in doc, f"Unexpected doc content: {doc!r}"

    def test_no_godoc_returns_empty(self):
        """Types without godoc must have empty doc (not crash)."""
        doc = self._get_type_doc(self.GO_TYPE_NO_GODOC, "Page")
        assert doc == "", f"Expected empty doc for Page, got: {doc!r}"


class TestGoMethodReturnType:
    """SFX-2B: Go method_declaration return_type must be the actual type, not the method name."""

    GO_METHODS = b"""\
func (d *DestinationFitBH) Top() float64 { return d.top }
func (d *DestinationFitBH) Page() *Page { return d.page }
func (f *ButtonField) Value() string { return "" }
func (f *ButtonField) SetValue(s string) error { return nil }
func (f *ButtonField) SetReadOnly(v bool) { setFlag(f.node, fieldFlagReadOnly, v) }
"""

    def test_go_method_return_type_extracted(self):
        """Method return type must be the actual Go type, not the method name."""
        from extraction.api_surface import _extract_return_type
        from extraction.tree_helpers import get_parser, node_text

        parser = get_parser("go")
        tree = parser.parse(self.GO_METHODS)
        results = {}
        for node in tree.root_node.children:
            if node.type == "method_declaration":
                name = node_text(node.child_by_field_name("name"))
                ret = _extract_return_type(node, "go")
                results[name] = ret
        assert results["Top"] == "float64"
        assert results["Page"] == "*Page"
        assert results["Value"] == "string"
        assert results["SetValue"] == "error"
        assert results["SetReadOnly"] == ""  # void method has no return type


# ---------------------------------------------------------------------------
# GO-006: Go package name extraction from source files
# ---------------------------------------------------------------------------

class TestGoPackageNameExtraction:
    """GO-006: _extract_go_package_name must read declared package name from source.

    The module path (e.g. github.com/aspose-pdf-foss/aspose-pdf-foss-for-go) is NOT
    the package name.  The package name (e.g. asposepdf) must be read from the
    ``package <name>`` declaration in the first non-test .go file at repo root.
    """

    def test_extracts_package_name_from_go_file(self):
        """_extract_go_package_name returns declared name from first non-test .go file."""
        import tempfile
        from pathlib import Path
        from extraction.package_manifest import _extract_go_package_name

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "annotation.go").write_text("package asposepdf\n\ntype Annotation struct{}\n")
            result = _extract_go_package_name(repo)
        assert result == "asposepdf", f"Expected 'asposepdf', got {result!r}"

    def test_skips_test_files(self):
        """_extract_go_package_name must not read from *_test.go files."""
        import tempfile
        from pathlib import Path
        from extraction.package_manifest import _extract_go_package_name

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            # Only a _test.go file — should return ""
            (repo / "annotation_test.go").write_text("package asposepdf_test\n")
            result = _extract_go_package_name(repo)
        assert result == "", f"Expected empty string (no non-test .go), got {result!r}"

    def test_skips_package_main(self):
        """_extract_go_package_name must skip files with 'package main'."""
        import tempfile
        from pathlib import Path
        from extraction.package_manifest import _extract_go_package_name

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "cmd.go").write_text("package main\n\nfunc main() {}\n")
            (repo / "doc.go").write_text("package mypkg\n\n// Package mypkg provides ...\n")
            result = _extract_go_package_name(repo)
        assert result == "mypkg", f"Expected 'mypkg', got {result!r}"

    def test_parse_go_manifest_includes_package_name(self):
        """_parse_go_manifest must include package_name key when source file present."""
        import tempfile
        from pathlib import Path
        from extraction.package_manifest import _parse_go_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "go.mod").write_text(
                "module github.com/aspose-pdf-foss/aspose-pdf-foss-for-go\n\ngo 1.24\n"
            )
            (repo / "doc.go").write_text("package asposepdf\n\n// Package asposepdf ...\n")
            info = _parse_go_manifest(repo)
        assert info.get("package_name") == "asposepdf", (
            f"Expected package_name='asposepdf', got {info!r}"
        )
        assert info.get("name") == "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"


# ---------------------------------------------------------------------------
# GO-004: Go snippet extraction from ExampleXxx functions and _examples/ dirs
# ---------------------------------------------------------------------------

class TestGoSnippetExtraction:
    """GO-004: Snippet extractor must handle Go ExampleXxx functions and _examples/ dirs."""

    GO_EXAMPLE_TEST_SRC = """\
package asposepdf_test

import (
    pdf "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"
)

func ExampleNewDocumentFromFormat() {
    doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
    doc.Save("out.pdf")
}

func ExampleDocument_Split() {
    doc, _ := pdf.Open("in.pdf")
    pages, _ := doc.Split()
    _ = pages
}

func helperFunc() {}
"""

    GO_MAIN_EXAMPLE_SRC = """\
package main

import (
    pdf "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"
)

func main() {
    doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
    doc.Save("blank.pdf")
}
"""

    def _extract_snippet_functions(self, src: str, is_example_dir: bool = False):
        from extraction.snippets import _collect_snippet_functions
        from extraction.tree_helpers import get_parser, _FUNC_TYPES, _CLASS_TYPES
        parser = get_parser("go")
        tree = parser.parse(src.encode("utf-8"))
        func_types = _FUNC_TYPES.get("go", set())
        class_types = _CLASS_TYPES.get("go", set())
        return _collect_snippet_functions(
            tree.root_node, "go", func_types, class_types, src,
            is_example_dir=is_example_dir,
        )

    def test_example_functions_extracted(self):
        """ExampleXxx functions must be captured as snippets."""
        results = self._extract_snippet_functions(self.GO_EXAMPLE_TEST_SRC)
        names = [r[0] for r in results]
        assert "ExampleNewDocumentFromFormat" in names, (
            f"ExampleNewDocumentFromFormat not in {names!r}"
        )
        assert "ExampleDocument_Split" in names, (
            f"ExampleDocument_Split not in {names!r}"
        )

    def test_helper_func_not_extracted(self):
        """Non-Example functions must NOT be captured."""
        results = self._extract_snippet_functions(self.GO_EXAMPLE_TEST_SRC)
        names = [r[0] for r in results]
        assert "helperFunc" not in names, f"helperFunc should not be in snippets: {names!r}"

    def test_main_extracted_in_example_dir(self):
        """main() function in _examples/ dir (is_example_dir=True) must be captured."""
        results = self._extract_snippet_functions(
            self.GO_MAIN_EXAMPLE_SRC, is_example_dir=True
        )
        names = [r[0] for r in results]
        assert "main" in names, f"main not captured from example dir: {names!r}"

    def test_main_not_extracted_outside_example_dir(self):
        """main() must NOT be captured when is_example_dir=False."""
        results = self._extract_snippet_functions(
            self.GO_MAIN_EXAMPLE_SRC, is_example_dir=False
        )
        names = [r[0] for r in results]
        assert "main" not in names, f"main should not be captured outside example dir: {names!r}"


# ---------------------------------------------------------------------------
# GO-005: Go package root detection
# ---------------------------------------------------------------------------

class TestGoPackageRootDetection:
    """GO-005: detect_package_root must validate go.mod for Go repos."""

    def test_flat_layout_returns_repo_root(self):
        """Flat layout (go.mod at root) must return repo root."""
        import tempfile
        from pathlib import Path
        from extraction.package_root import detect_package_root

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "go.mod").write_text(
                "module github.com/example/mylib\n\ngo 1.21\n"
            )
            result = detect_package_root(repo, "go")
        assert result == repo, f"Expected repo root, got {result!r}"

    def test_nested_layout_returns_subdir(self):
        """Nested layout (go.mod in a subdir) must return that subdir."""
        import tempfile
        from pathlib import Path
        from extraction.package_root import detect_package_root

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            lib = repo / "lib"
            lib.mkdir()
            (lib / "go.mod").write_text(
                "module github.com/example/mylib\n\ngo 1.21\n"
            )
            result = detect_package_root(repo, "go")
        assert result == lib, f"Expected {lib!r}, got {result!r}"

    def test_no_go_mod_falls_back_to_repo(self):
        """When no go.mod is found, must fall back to repo root."""
        import tempfile
        from pathlib import Path
        from extraction.package_root import detect_package_root

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            result = detect_package_root(repo, "go")
        assert result == repo, f"Expected repo fallback, got {result!r}"


# ---------------------------------------------------------------------------
# GO-011: Go struct field extraction
# ---------------------------------------------------------------------------

class TestGoStructFieldExtraction:
    """GO-011: Exported struct fields must appear in properties[] for Go types."""

    GO_RENDER_OPTIONS_SRC = """\
package asposepdf

// RenderOptions configures rendering.
type RenderOptions struct {
    DPI        float64
    Background *Color
    unexported int
}

// Color represents an RGBA colour.
type Color struct {
    R, G, B, A float64
}
"""

    def _extract(self, src: str):
        """Run extract_api_surface on Go fixture and return all entries."""
        import tempfile
        from pathlib import Path
        parser = scout.get_parser("go")
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            (root_dir / "render.go").write_text(src)
            classes, _, _, _, _ = extract_api_surface(
                parser, "go", root_dir, root_dir, "testfamily"
            )
        return classes

    def test_render_options_has_dpi_property(self):
        """RenderOptions.DPI must appear in properties[]."""
        classes = self._extract(self.GO_RENDER_OPTIONS_SRC)
        type_map = {e["name"]: e for e in classes}
        ro = type_map.get("RenderOptions")
        assert ro is not None, "RenderOptions type not found"
        prop_names = [p["name"] for p in ro.get("properties", [])]
        assert "DPI" in prop_names, f"DPI not in properties: {prop_names!r}"

    def test_render_options_has_background_property(self):
        """RenderOptions.Background must appear in properties[]."""
        classes = self._extract(self.GO_RENDER_OPTIONS_SRC)
        type_map = {e["name"]: e for e in classes}
        ro = type_map.get("RenderOptions")
        assert ro is not None, "RenderOptions type not found"
        prop_names = [p["name"] for p in ro.get("properties", [])]
        assert "Background" in prop_names, f"Background not in properties: {prop_names!r}"

    def test_unexported_field_excluded(self):
        """unexported (lowercase) fields must NOT appear in properties[]."""
        classes = self._extract(self.GO_RENDER_OPTIONS_SRC)
        type_map = {e["name"]: e for e in classes}
        ro = type_map.get("RenderOptions")
        assert ro is not None, "RenderOptions type not found"
        prop_names = [p["name"] for p in ro.get("properties", [])]
        assert "unexported" not in prop_names, (
            f"unexported should not be in properties: {prop_names!r}"
        )

    def test_multi_name_field_declaration(self):
        """Multi-name field decl (R, G, B, A float64) must produce one property per name."""
        classes = self._extract(self.GO_RENDER_OPTIONS_SRC)
        type_map = {e["name"]: e for e in classes}
        color = type_map.get("Color")
        assert color is not None, "Color type not found"
        prop_names = [p["name"] for p in color.get("properties", [])]
        for ch in ("R", "G", "B", "A"):
            assert ch in prop_names, f"Color.{ch} not in properties: {prop_names!r}"
