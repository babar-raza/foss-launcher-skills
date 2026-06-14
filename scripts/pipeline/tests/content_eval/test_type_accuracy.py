"""Unit tests for TypeAccuracyEvaluator (S-Fix-13)."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from content_eval.models import Page
from content_eval.evaluators.type_accuracy import TypeAccuracyEvaluator


def _make_page(content: str, filepath: str) -> Page:
    """Create a Page from markdown content string with explicit filepath."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


def _cpp_page(body: str) -> Page:
    """Convenience: create a cpp platform reference page."""
    content = textwrap.dedent(f"""\
        ---
        title: Test
        ---
        {body}
    """)
    return _make_page(content, "content/reference.aspose.org/en/3d/cpp/test.md")


def _non_cpp_page(body: str) -> Page:
    """Convenience: create a dotnet platform reference page."""
    content = textwrap.dedent(f"""\
        ---
        title: Test
        ---
        {body}
    """)
    return _make_page(content, "content/reference.aspose.org/en/3d/dotnet/test.md")


# ---------------------------------------------------------------------------
# Test: const std::string& → WARN
# ---------------------------------------------------------------------------

class TestStringRefCheck:
    def setup_method(self):
        self.ev = TypeAccuracyEvaluator()

    def test_const_string_ref_in_cpp_code_produces_warn(self):
        page = _cpp_page(textwrap.dedent("""\
            Example:

            ```cpp
            void Open(const std::string& path);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "const string&" in f.message or "string&" in f.message]
        assert len(warn) >= 1
        assert warn[0].level == "WARN"
        assert warn[0].category == "TA"

    def test_const_string_ref_with_space_before_ampersand(self):
        """Handles 'const std::string &name' variant."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            bool Load(const std::string &name, int flags);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "string&" in f.message or "string_view" in f.suggestion]
        assert len(warn) >= 1
        assert warn[0].level == "WARN"

    def test_string_view_already_correct_no_finding(self):
        """If std::string_view is used correctly, no finding emitted."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            void Open(std::string_view path);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "string" in f.message.lower() and f.level == "WARN"]
        assert len(warn) == 0

    def test_non_cpp_platform_no_finding(self):
        """Guard: non-cpp page must produce zero findings even with string& pattern."""
        page = _non_cpp_page(textwrap.dedent("""\
            ```csharp
            void Open(const std::string& path);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Test: float for geometry properties → WARN
# ---------------------------------------------------------------------------

class TestFloatGeometryCheck:
    def setup_method(self):
        self.ev = TypeAccuracyEvaluator()

    def test_float_x_produces_warn(self):
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            float x = 0.0f;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "`x`" in f.message and "float" in f.message]
        assert len(warn) >= 1
        assert warn[0].level == "WARN"
        assert warn[0].category == "TA"

    def test_float_width_produces_warn(self):
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            float width = GetWidth();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "`width`" in f.message]
        assert len(warn) >= 1
        assert warn[0].level == "WARN"

    def test_float_height_produces_warn(self):
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            float height = 100.0f;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "`height`" in f.message]
        assert len(warn) >= 1

    def test_float_rotation_produces_warn(self):
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            void SetRotation(float rotation);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "`rotation`" in f.message]
        assert len(warn) >= 1

    def test_float_y_produces_warn(self):
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            float y;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if "`y`" in f.message]
        assert len(warn) >= 1

    def test_double_x_no_finding(self):
        """double x is correct — no finding."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            double x = 0.0;
            double y = 0.0;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        geom_warn = [f for f in findings if "Geometry property" in f.message]
        assert len(geom_warn) == 0

    def test_float_non_geom_name_no_finding(self):
        """float used for a non-geometry variable name — no finding."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            float opacity = 1.0f;
            float scale = 2.5f;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        geom_warn = [f for f in findings if "Geometry property" in f.message]
        assert len(geom_warn) == 0

    def test_non_cpp_platform_float_no_finding(self):
        """Guard: non-cpp page produces zero findings."""
        page = _non_cpp_page(textwrap.dedent("""\
            ```csharp
            float x = 0.0f;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Test: No issues → zero findings
# ---------------------------------------------------------------------------

class TestCleanCppPage:
    def setup_method(self):
        self.ev = TypeAccuracyEvaluator()

    def test_clean_cpp_page_no_findings(self):
        """A well-typed cpp page should produce no type_accuracy findings."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            #include <aspose/3d/Scene.h>
            using namespace Aspose::ThreeD;

            auto scene = System::MakeObject<Scene>();
            scene->Open(u"input.fbx");
            scene->Save(u"output.obj", FileFormat::WavefrontOBJ);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        # No WARN or INFO from type_accuracy expected
        assert all(f.evaluator != "type_accuracy" for f in findings) or len(findings) == 0

    def test_no_cpp_code_blocks_no_findings(self):
        """Page with only prose and non-cpp code blocks → no findings."""
        page = _cpp_page(textwrap.dedent("""\
            Some prose about the API.

            ```bash
            cmake -DCMAKE_BUILD_TYPE=Release ..
            ```
        """))
        findings = self.ev.evaluate(page, None)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Test: Non-cpp platform guard
# ---------------------------------------------------------------------------

class TestNonCppPlatformGuard:
    def setup_method(self):
        self.ev = TypeAccuracyEvaluator()

    def test_dotnet_page_returns_empty(self):
        """dotnet platform → evaluator must return empty list."""
        page = _non_cpp_page(textwrap.dedent("""\
            ```csharp
            void Open(const std::string& path);
            float x = 0;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        assert findings == []

    def test_python_page_returns_empty(self):
        """python platform → evaluator must return empty list."""
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: Test
                ---
                ```cpp
                float x = 0.0f;
                const std::string& path;
                ```
            """),
            "content/reference.aspose.org/en/3d/python/test.md",
        )
        findings = self.ev.evaluate(page, None)
        assert findings == []

    def test_java_page_returns_empty(self):
        """java platform → evaluator must return empty list."""
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: Test
                ---
                ```cpp
                float width;
                ```
            """),
            "content/reference.aspose.org/en/3d/java/test.md",
        )
        findings = self.ev.evaluate(page, None)
        assert findings == []


# ---------------------------------------------------------------------------
# Test: Static modifier check
# ---------------------------------------------------------------------------

class TestStaticModifierCheck:
    def setup_method(self):
        self.ev = TypeAccuracyEvaluator()

    def test_static_method_no_api_surface_produces_info(self):
        """When api_surface.json is absent, static decl → INFO finding."""
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: Test
                ---
                ```cpp
                static System::SharedPtr<Scene> Open(std::string_view path);
                ```
            """),
            # Use a family that definitely has no knowledge/ directory
            "content/reference.aspose.org/en/nonexistent_foss_lib/cpp/test.md",
        )
        findings = self.ev.evaluate(page, None)
        static_info = [f for f in findings if "static" in f.message.lower() and f.level == "INFO"]
        assert len(static_info) >= 1
        assert static_info[0].category == "TA"

    def test_no_static_keyword_no_static_finding(self):
        """Code without 'static' keyword should not produce static findings."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            void Open(std::string_view path);
            double GetWidth() const;
            ```
        """))
        findings = self.ev.evaluate(page, None)
        static_findings = [f for f in findings if "static" in f.message.lower()]
        assert len(static_findings) == 0


# ---------------------------------------------------------------------------
# Test: Multiple findings in one block
# ---------------------------------------------------------------------------

class TestMultipleFindings:
    def setup_method(self):
        self.ev = TypeAccuracyEvaluator()

    def test_both_patterns_in_same_block(self):
        """Both string& and float-geometry in the same block → two warnings."""
        page = _cpp_page(textwrap.dedent("""\
            ```cpp
            void SetBounds(const std::string& name, float x, float y);
            ```
        """))
        findings = self.ev.evaluate(page, None)
        warn = [f for f in findings if f.level == "WARN" and f.category == "TA"]
        # Expect: 1 string& WARN + 2 float-geometry WARNs (x and y)
        assert len(warn) >= 3


# ---------------------------------------------------------------------------
# Helpers for C#/Java tests (Check 6)
# ---------------------------------------------------------------------------

def _csharp_page(body: str) -> Page:
    """Create a .NET platform docs page with C# code blocks."""
    content = textwrap.dedent(f"""\
        ---
        title: Test
        ---
        {body}
    """)
    return _make_page(content, "content/docs.aspose.org/en/pdf/net/test.md")


def _java_page(body: str) -> Page:
    """Create a Java platform docs page."""
    content = textwrap.dedent(f"""\
        ---
        title: Test
        ---
        {body}
    """)
    return _make_page(content, "content/docs.aspose.org/en/pdf/java/test.md")


def _write_api_surface(family: str, platform: str, classes: list[dict],
                       root: Path | None = None) -> None:
    """Write a temporary api_surface.json for tests.

    When *root* is provided, writes under that directory instead of the real
    ``knowledge/`` tree — keeping tests isolated from production artifacts.
    """
    import json
    base = root if root is not None else Path("knowledge")
    merged_dir = base / family / platform / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "api_surface.json").write_text(
        json.dumps(classes), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Test: Check 6 — static class instantiation (C#/Java)
# ---------------------------------------------------------------------------

class TestStaticClassInstantiation:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Write api_surface.json into tmp_path and redirect KNOWLEDGE_ROOT."""
        import content_eval.evaluators.type_accuracy as _ta_mod
        monkeypatch.setattr(_ta_mod, "KNOWLEDGE_ROOT", tmp_path)
        self._knowledge_root = tmp_path
        self.ev = TypeAccuracyEvaluator()
        _write_api_surface("pdf", "net", [
            {"name": "FieldDateTimeFormatter", "kind": "class_declaration",
             "is_static": True, "methods": [], "properties": [], "visibility": "public"},
            {"name": "FieldNumberCurrencyFormatter", "kind": "class_declaration",
             "methods": [], "properties": [], "visibility": "public"},
            {"name": "AbstractBase", "kind": "class_declaration",
             "is_abstract": True, "methods": [], "properties": [], "visibility": "public"},
        ], root=tmp_path)

    def test_new_static_class_produces_warn(self):
        """new FieldDateTimeFormatter() → FAIL (static class, C#)."""
        page = _csharp_page(textwrap.dedent("""\
            ```csharp
            var fmt = new FieldDateTimeFormatter();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        static_fail = [f for f in findings if "static" in f.message and f.level == "FAIL"]
        assert len(static_fail) == 1
        assert static_fail[0].category == "TA"
        assert "FieldDateTimeFormatter" in static_fail[0].message

    def test_new_regular_class_no_finding(self):
        """new FieldNumberCurrencyFormatter() → no finding (not static)."""
        page = _csharp_page(textwrap.dedent("""\
            ```csharp
            var fmt = new FieldNumberCurrencyFormatter();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        static_warn = [f for f in findings if "static" in f.message or "abstract" in f.message]
        assert len(static_warn) == 0

    def test_new_abstract_class_produces_warn(self):
        """new AbstractBase() → WARN (abstract class)."""
        page = _csharp_page(textwrap.dedent("""\
            ```csharp
            var obj = new AbstractBase();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        abstract_warn = [f for f in findings if "abstract" in f.message and f.level == "WARN"]
        assert len(abstract_warn) == 1
        assert "AbstractBase" in abstract_warn[0].message

    def test_class_not_in_surface_no_finding(self):
        """new UnknownClass() → no finding (not in api_surface)."""
        page = _csharp_page(textwrap.dedent("""\
            ```csharp
            var obj = new UnknownClass();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        static_warn = [f for f in findings if "static" in f.message or "abstract" in f.message]
        assert len(static_warn) == 0

    def test_java_static_class_is_allowed(self):
        """Java static class → no finding (Java static = nested static, instantiable)."""
        _write_api_surface("pdf", "java", [
            {"name": "StaticHelper", "kind": "class_declaration",
             "is_static": True, "methods": [], "properties": [], "visibility": "public"},
        ], root=self._knowledge_root)
        page = _java_page(textwrap.dedent("""\
            ```java
            StaticHelper h = new StaticHelper();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        static_warn = [f for f in findings if "static" in f.message and f.level == "WARN"]
        assert len(static_warn) == 0

    def test_java_abstract_class_produces_warn(self):
        """Java abstract class → WARN (abstract applies to both languages)."""
        _write_api_surface("pdf", "java", [
            {"name": "AbstractProcessor", "kind": "class_declaration",
             "is_abstract": True, "methods": [], "properties": [], "visibility": "public"},
        ], root=self._knowledge_root)
        page = _java_page(textwrap.dedent("""\
            ```java
            AbstractProcessor p = new AbstractProcessor();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        abstract_warn = [f for f in findings if "abstract" in f.message and f.level == "WARN"]
        assert len(abstract_warn) == 1

    def test_python_platform_not_checked(self):
        """Python platform pages are not checked by Check 6."""
        _write_api_surface("pdf", "python", [
            {"name": "StaticHelper", "kind": "class_declaration",
             "is_static": True, "methods": [], "properties": [], "visibility": "public"},
        ], root=self._knowledge_root)
        content = textwrap.dedent("""\
            ---
            title: Test
            ---
            ```python
            obj = StaticHelper()
            ```
        """)
        page = _make_page(content, "content/docs.aspose.org/en/pdf/python/test.md")
        findings = self.ev.evaluate(page, None)
        static_warn = [f for f in findings if "static" in f.message]
        assert len(static_warn) == 0

    def test_missing_is_static_field_no_finding(self):
        """Class without is_static key → no finding (graceful degradation)."""
        _write_api_surface("pdf", "net", [
            {"name": "OldClass", "kind": "class_declaration",
             "methods": [], "properties": [], "visibility": "public"},
        ], root=self._knowledge_root)
        page = _csharp_page(textwrap.dedent("""\
            ```csharp
            var obj = new OldClass();
            ```
        """))
        findings = self.ev.evaluate(page, None)
        static_warn = [f for f in findings if "static" in f.message or "abstract" in f.message]
        assert len(static_warn) == 0
