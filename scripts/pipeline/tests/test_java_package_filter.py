"""SYS-PKG-001: Java internal-package exclusion filter regression tests.

Covers:
- Unit tests for _is_excluded_java_package() helper (segment vs substring semantics)
- Unit tests for _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS constant
- Integration tests for extract_api_surface() with Java internal/public packages
- Cross-language safety: non-Java must not be affected
- Override: excluded_package_segments=frozenset() disables filtering

Related plan: C:\\Users\\prora\\.claude\\plans\\fuzzy-cuddling-honey.md
Blocker classification: systemic blocker — root cause fix at scout layer.
"""
import textwrap
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from extraction.api_surface import (
    _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS,
    _is_excluded_java_package,
    extract_api_surface,
)
import scout


# ---------------------------------------------------------------------------
# Unit tests: _is_excluded_java_package
# ---------------------------------------------------------------------------

class TestIsExcludedJavaPackage:
    """_is_excluded_java_package must use exact segment matching, not substring."""

    def test_internal_segment_excluded(self):
        """Package with 'internal' as a dot-segment must be excluded."""
        assert _is_excluded_java_package(
            "com.aspose.slides.internal.dx",
            frozenset({"internal", "impl"}),
        )

    def test_impl_segment_excluded(self):
        """Package with 'impl' as a dot-segment must be excluded."""
        assert _is_excluded_java_package(
            "com.aspose.slides.impl.utils",
            frozenset({"internal", "impl"}),
        )

    def test_internal_at_end_excluded(self):
        """Package ending in 'internal' must be excluded."""
        assert _is_excluded_java_package(
            "com.aspose.slides.internal",
            frozenset({"internal"}),
        )

    def test_normal_package_not_excluded(self):
        """Standard public package must not be excluded."""
        assert not _is_excluded_java_package(
            "com.aspose.slides",
            frozenset({"internal", "impl"}),
        )

    def test_international_not_excluded(self):
        """'international' must NOT match 'internal' — segment not substring."""
        assert not _is_excluded_java_package(
            "com.aspose.international",
            frozenset({"internal", "impl"}),
        )

    def test_implementation_not_excluded(self):
        """'implementation' must NOT match 'impl' — segment not substring."""
        assert not _is_excluded_java_package(
            "com.aspose.slides.implementation",
            frozenset({"impl"}),
        )

    def test_empty_package_not_excluded(self):
        """Empty package string must return False, not raise."""
        assert not _is_excluded_java_package("", frozenset({"internal", "impl"}))

    def test_empty_segments_not_excluded(self):
        """Empty excluded_segments frozenset must return False always."""
        assert not _is_excluded_java_package("com.aspose.slides.internal", frozenset())

    def test_custom_segments_respected(self):
        """Custom segment exclusion works correctly."""
        assert _is_excluded_java_package("com.example.foo", frozenset({"foo"}))
        assert not _is_excluded_java_package("com.example.foo", frozenset({"bar"}))

    def test_single_segment_package(self):
        """Single-segment package (e.g. 'internal') must be excluded if matched."""
        assert _is_excluded_java_package("internal", frozenset({"internal"}))
        assert not _is_excluded_java_package("slides", frozenset({"internal"}))


# ---------------------------------------------------------------------------
# Unit tests: _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS
# ---------------------------------------------------------------------------

class TestJavaDefaultExcludedSegments:
    """Constant must contain canonical exclusion segments, nothing more."""

    def test_contains_internal(self):
        assert "internal" in _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS

    def test_contains_impl(self):
        assert "impl" in _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS

    def test_does_not_contain_normal_segments(self):
        """Must not accidentally blacklist normal package segments."""
        for safe_seg in ("slides", "aspose", "utils", "common", "api"):
            assert safe_seg not in _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS, (
                f"'{safe_seg}' must not be in default exclusion set"
            )

    def test_is_frozenset(self):
        assert isinstance(_JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS, frozenset)


# ---------------------------------------------------------------------------
# Integration tests: extract_api_surface with Java source files
# ---------------------------------------------------------------------------

def _write_java_file(directory: Path, filename: str, code: str) -> Path:
    """Write a Java source file and return its path."""
    f = directory / filename
    f.write_text(textwrap.dedent(code))
    return f


class TestExtractApiSurfaceJavaPackageFilter:
    """extract_api_surface must exclude Java classes in internal/impl packages."""

    def test_internal_package_class_excluded_by_default(self, tmp_path):
        """Class in *.internal.* package must be excluded from output by default."""
        _write_java_file(tmp_path, "AppPropertiesPart.java", """
            package com.aspose.slides.internal.pptx;
            public class AppPropertiesPart {
                public void read() {}
            }
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides")
        names = [c["name"] for c in classes]
        assert "AppPropertiesPart" not in names, (
            "AppPropertiesPart in internal package must be excluded by default"
        )

    def test_impl_package_class_excluded_by_default(self, tmp_path):
        """Class in *.impl.* package must be excluded by default."""
        _write_java_file(tmp_path, "SlideImpl.java", """
            package com.aspose.slides.impl;
            public class SlideImpl {
                public String getTitle() { return ""; }
            }
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides")
        names = [c["name"] for c in classes]
        assert "SlideImpl" not in names, (
            "SlideImpl in impl package must be excluded by default"
        )

    def test_public_package_class_included(self, tmp_path):
        """Class in a normal public package must still be extracted."""
        _write_java_file(tmp_path, "Presentation.java", """
            package com.aspose.slides;
            public class Presentation {
                public void save(String path) {}
            }
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides")
        names = [c["name"] for c in classes]
        assert "Presentation" in names, (
            "Presentation in public package must be included"
        )

    def test_international_package_not_excluded(self, tmp_path):
        """'international' segment must NOT be excluded by the 'internal' rule."""
        _write_java_file(tmp_path, "LocaleHelper.java", """
            package com.aspose.slides.international;
            public class LocaleHelper {
                public String getLocale() { return "en"; }
            }
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides")
        names = [c["name"] for c in classes]
        assert "LocaleHelper" in names, (
            "LocaleHelper in 'international' package must NOT be excluded — "
            "segment matching, not substring"
        )

    def test_override_with_empty_frozenset_disables_filtering(self, tmp_path):
        """excluded_package_segments=frozenset() must disable all package filtering."""
        _write_java_file(tmp_path, "AppPropertiesPart.java", """
            package com.aspose.slides.internal.pptx;
            public class AppPropertiesPart {
                public void read() {}
            }
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides",
            excluded_package_segments=frozenset(),  # disable filtering
        )
        names = [c["name"] for c in classes]
        assert "AppPropertiesPart" in names, (
            "With excluded_package_segments=frozenset(), no package filtering should occur"
        )

    def test_custom_exclusion_segments_respected(self, tmp_path):
        """Custom excluded_package_segments override must be respected."""
        _write_java_file(tmp_path, "SecretHelper.java", """
            package com.aspose.slides.secret;
            public class SecretHelper {}
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides",
            excluded_package_segments=frozenset({"secret"}),
        )
        names = [c["name"] for c in classes]
        assert "SecretHelper" not in names, (
            "SecretHelper must be excluded by custom excluded_package_segments={'secret'}"
        )

    def test_no_package_declaration_class_included(self, tmp_path):
        """Java class with no package declaration must still be included."""
        _write_java_file(tmp_path, "SimpleClass.java", """
            public class SimpleClass {
                public void doWork() {}
            }
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides")
        names = [c["name"] for c in classes]
        assert "SimpleClass" in names, (
            "SimpleClass with no package declaration must be included"
        )

    def test_mixed_file_set(self, tmp_path):
        """Mixed internal+public classes: only public ones emitted."""
        _write_java_file(tmp_path, "Presentation.java", """
            package com.aspose.slides;
            public class Presentation {
                public void save(String path) {}
            }
        """)
        (tmp_path / "internal_sub").mkdir()
        _write_java_file(tmp_path / "internal_sub", "InternalHelper.java", """
            package com.aspose.slides.internal;
            public class InternalHelper {}
        """)
        parser = scout.get_parser("java")
        classes, _, _, _, _ = extract_api_surface(
            parser, "java", tmp_path, tmp_path, "slides")
        names = [c["name"] for c in classes]
        assert "Presentation" in names
        assert "InternalHelper" not in names


# ---------------------------------------------------------------------------
# Cross-language safety: non-Java must not be affected
# ---------------------------------------------------------------------------

class TestNonJavaNotAffected:
    """Package filtering is Java-only; other languages must be unaffected."""

    def test_python_class_not_excluded(self, tmp_path):
        """Python class named 'InternalHelper' must be extracted normally."""
        f = tmp_path / "helpers.py"
        f.write_text(textwrap.dedent("""
            class InternalHelper:
                def help(self): pass
        """))
        parser = scout.get_parser("python")
        classes, _, _, _, _ = extract_api_surface(
            parser, "python", tmp_path, tmp_path, "test")
        names = [c["name"] for c in classes]
        assert "InternalHelper" in names, (
            "Python InternalHelper must be extracted — filter is Java-only"
        )

    def test_explicit_excluded_segments_for_non_java_has_no_effect(self, tmp_path):
        """Even with excluded_package_segments set, non-Java is unaffected."""
        f = tmp_path / "impl_module.py"
        f.write_text(textwrap.dedent("""
            class ImplClass:
                def run(self): pass
        """))
        parser = scout.get_parser("python")
        classes, _, _, _, _ = extract_api_surface(
            parser, "python", tmp_path, tmp_path, "test",
            excluded_package_segments=frozenset({"impl"}),
        )
        names = [c["name"] for c in classes]
        assert "ImplClass" in names, (
            "Python ImplClass must be extracted regardless of excluded_package_segments"
        )
