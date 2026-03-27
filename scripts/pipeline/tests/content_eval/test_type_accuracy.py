"""Unit tests for TypeAccuracyEvaluator (S-Fix-13)."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

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
