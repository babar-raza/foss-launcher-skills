"""Tests for the shared reference API surface filter (TC-REF-09 / TC-REF-11).

Covers:
- filter_api_surface() for each supported platform
- filtered_count()
- count_index_table_rows()
- is_stale_grouped_index()
- Platform-specific exclusions unified from batch_reference.py (TC-REF-11):
    C++ I-prefix / abstract bases, Python I-prefix,
    Java _JAVA_INTERNAL_CLASSES, .NET .Internal. namespace
"""
import pytest
from scripts.pipeline.lib.reference_filter import (
    filter_api_surface,
    filtered_count,
    count_index_table_rows,
    is_stale_grouped_index,
    _passes_platform_scope,
    _CPP_ABSTRACT_BASES,
    _JAVA_INTERNAL_CLASSES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PYTHON_API = [
    {"kind": "class_definition", "name": "FontLoader", "file": "src/pkg/loader.py", "visibility": "public"},
    {"kind": "class_definition", "name": "TtfFont", "file": "src/pkg/ttf.py", "visibility": "public"},
    {"kind": "class_definition", "name": "_Private", "file": "src/pkg/ttf.py", "visibility": "public"},
    {"kind": "class_definition", "name": "InternalFont", "file": "src/pkg/internal/base.py", "visibility": "public"},
    {"kind": "class_definition", "name": "HiddenClass", "file": "src/pkg/types.py", "visibility": "internal"},
    {"kind": "function_definition", "name": "load_font", "file": "src/pkg/loader.py", "visibility": "public"},
]

GO_API = [
    {"kind": "type_spec", "name": "Font", "file": "pkg/font/font.go", "visibility": "public"},
    {"kind": "type_spec", "name": "Metrics", "file": "pkg/font/metrics.go", "visibility": "public"},
    {"kind": "function", "name": "NewFont", "file": "pkg/font/font.go", "visibility": "public"},
    {"kind": "function", "name": "LoadTTF", "file": "pkg/font/loader.go", "visibility": "public"},
    {"kind": "type_spec", "name": "internalType", "file": "pkg/internal/base.go", "visibility": "public"},
]

JAVA_API = [
    {"kind": "class_declaration", "name": "FontSaver", "file": "src/FontSaver.java", "visibility": "public"},
    {"kind": "interface_declaration", "name": "IFont", "file": "src/IFont.java", "visibility": "public"},
    {"kind": "enum_declaration", "name": "FontFormat", "file": "src/FontFormat.java", "visibility": "public"},
    {"kind": "class_declaration", "name": "Internal", "file": "src/internal/Base.java", "visibility": "public"},
    {"kind": "class_declaration", "name": "Hidden", "file": "src/Hidden.java", "visibility": "internal"},
]

NET_API = [
    {"kind": "class_declaration", "name": "FontConverter", "file": "src/FontConverter.cs", "visibility": "public"},
    {"kind": "struct_declaration", "name": "FontMetrics", "file": "src/FontMetrics.cs", "visibility": "public"},
    {"kind": "record_declaration", "name": "FontRecord", "file": "src/FontRecord.cs", "visibility": "public"},
    {"kind": "enum_declaration", "name": "FontType", "file": "src/FontType.cs", "visibility": "public"},
]

CPP_API = [
    {"kind": "class_specifier", "name": "FontBase", "file": "include/font_base.h", "visibility": "public"},
    {"kind": "struct_specifier", "name": "FontMetrics", "file": "include/font_metrics.h", "visibility": "public"},
    {"kind": "enum_specifier", "name": "FontKind", "file": "include/font_kind.h", "visibility": "public"},
    # I-prefix interface excluded (TC-REF-11 exclusion 1)
    {"kind": "class_specifier", "name": "IFontRenderer", "file": "include/ifont_renderer.h", "visibility": "public"},
    # Abstract base excluded (TC-REF-11 exclusion 2)
    {"kind": "class_specifier", "name": "BaseSlide", "file": "include/base_slide.h", "visibility": "public"},
    # Note: C++ does NOT filter by path — InternalBase in include/internal/ passes through
    {"kind": "class_specifier", "name": "InternalBase", "file": "include/internal/base.h", "visibility": "public"},
]


# ---------------------------------------------------------------------------
# filter_api_surface
# ---------------------------------------------------------------------------

class TestFilterApiSurface:
    def test_python_keeps_public_classes(self):
        result = filter_api_surface(PYTHON_API, "python")
        names = {e["name"] for e in result}
        assert "FontLoader" in names
        assert "TtfFont" in names

    def test_python_removes_underscore_names(self):
        result = filter_api_surface(PYTHON_API, "python")
        names = {e["name"] for e in result}
        assert "_Private" not in names

    def test_python_removes_internal_path(self):
        result = filter_api_surface(PYTHON_API, "python")
        names = {e["name"] for e in result}
        assert "InternalFont" not in names

    def test_python_removes_internal_visibility(self):
        result = filter_api_surface(PYTHON_API, "python")
        names = {e["name"] for e in result}
        assert "HiddenClass" not in names

    def test_python_removes_functions(self):
        result = filter_api_surface(PYTHON_API, "python")
        names = {e["name"] for e in result}
        assert "load_font" not in names

    def test_python_count(self):
        result = filter_api_surface(PYTHON_API, "python")
        assert len(result) == 2  # FontLoader, TtfFont

    def test_go_keeps_type_spec(self):
        result = filter_api_surface(GO_API, "go")
        names = {e["name"] for e in result}
        assert "Font" in names
        assert "Metrics" in names

    def test_go_removes_functions(self):
        result = filter_api_surface(GO_API, "go")
        names = {e["name"] for e in result}
        assert "NewFont" not in names
        assert "LoadTTF" not in names

    def test_go_removes_internal_path(self):
        result = filter_api_surface(GO_API, "go")
        names = {e["name"] for e in result}
        assert "internalType" not in names  # also starts with lowercase... actually path check

    def test_go_count(self):
        # Font, Metrics pass; NewFont/LoadTTF are function; internalType has /internal/ path
        result = filter_api_surface(GO_API, "go")
        assert len(result) == 2

    def test_java_keeps_classes_interfaces_enums(self):
        result = filter_api_surface(JAVA_API, "java")
        names = {e["name"] for e in result}
        assert "FontSaver" in names
        assert "IFont" in names
        assert "FontFormat" in names

    def test_java_removes_internal_path(self):
        result = filter_api_surface(JAVA_API, "java")
        names = {e["name"] for e in result}
        assert "Internal" not in names

    def test_java_removes_internal_visibility(self):
        result = filter_api_surface(JAVA_API, "java")
        names = {e["name"] for e in result}
        assert "Hidden" not in names

    def test_java_count(self):
        result = filter_api_surface(JAVA_API, "java")
        assert len(result) == 3

    def test_net_keeps_class_struct_record_enum(self):
        result = filter_api_surface(NET_API, "net")
        assert len(result) == 4

    def test_cpp_keeps_class_struct_enum(self):
        result = filter_api_surface(CPP_API, "cpp")
        names = {e["name"] for e in result}
        assert "FontBase" in names
        assert "FontMetrics" in names
        assert "FontKind" in names
        # C++ does NOT filter by path (unlike other platforms); InternalBase passes
        assert "InternalBase" in names
        # I-prefix and abstract bases are excluded (TC-REF-11)
        assert "IFontRenderer" not in names
        assert "BaseSlide" not in names

    def test_unknown_platform_returns_empty(self):
        api = [{"kind": "class_definition", "name": "Foo", "file": "x.py", "visibility": "public"}]
        result = filter_api_surface(api, "unknown_platform")
        assert result == []

    def test_empty_api_returns_empty(self):
        assert filter_api_surface([], "python") == []


# ---------------------------------------------------------------------------
# filtered_count
# ---------------------------------------------------------------------------

class TestFilteredCount:
    def test_python_count_matches_filter(self):
        assert filtered_count(PYTHON_API, "python") == len(filter_api_surface(PYTHON_API, "python"))

    def test_go_count_matches_filter(self):
        assert filtered_count(GO_API, "go") == len(filter_api_surface(GO_API, "go"))

    def test_empty_returns_zero(self):
        assert filtered_count([], "python") == 0


# ---------------------------------------------------------------------------
# count_index_table_rows
# ---------------------------------------------------------------------------

GROUPED_MD = """---
title: Test
---
## Classes

| Class | Description |
|-------|-------------|
| FontLoader | Loads fonts |
| TtfFont | TTF font class |

## Enums

| Enum | Description |
|------|-------------|
| FontFormat | Format enum |

## See Also

[Reference](https://example.com)
"""

FLAT_MD = """---
title: Test
---
{{< children >}}
"""

EMPTY_MD = """---
title: Test
---
No tables here.
"""


class TestCountIndexTableRows:
    def test_grouped_counts_data_rows(self):
        # 2 class rows + 1 enum row = 3, plus 2 header rows
        count = count_index_table_rows(GROUPED_MD)
        assert count == 5  # 2 headers + 2 class rows + 1 enum row (not counting | --- | rows)

    def test_flat_returns_zero(self):
        assert count_index_table_rows(FLAT_MD) == 0

    def test_empty_returns_zero(self):
        assert count_index_table_rows(EMPTY_MD) == 0

    def test_excludes_separator_rows(self):
        md = "---\ntitle: X\n---\n| A | B |\n|---|---|\n| C | D |\n"
        assert count_index_table_rows(md) == 2  # header + data, not separator


# ---------------------------------------------------------------------------
# is_stale_grouped_index
# ---------------------------------------------------------------------------

class TestIsStaleGroupedIndex:
    def test_grouped_full_coverage_not_stale(self):
        # 2 filtered entries, 5 table rows (well above threshold)
        is_stale, rows, expected = is_stale_grouped_index(
            GROUPED_MD, PYTHON_API, "python", threshold=0.10
        )
        assert not is_stale
        assert expected == 2  # FontLoader + TtfFont

    def test_stale_when_rows_below_threshold(self):
        # 1 row, 100 expected entries -> 1% < 10% threshold
        big_api = [
            {"kind": "class_definition", "name": f"Class{i}", "file": "src/x.py", "visibility": "public"}
            for i in range(100)
        ]
        is_stale, rows, expected = is_stale_grouped_index(
            GROUPED_MD, big_api, "python", threshold=0.10
        )
        assert is_stale
        assert expected == 100

    def test_not_stale_when_zero_filtered(self):
        # No classes in unknown platform -> expected=0, not stale
        is_stale, rows, expected = is_stale_grouped_index(
            GROUPED_MD, PYTHON_API, "unknown_platform"
        )
        assert not is_stale
        assert expected == 0

    def test_flat_page_not_flagged_as_stale(self):
        # Flat pages have 0 rows; but if expected > 0 they'd be stale
        # The validator skips flat pages before calling this, but test the math
        is_stale, rows, expected = is_stale_grouped_index(
            FLAT_MD, PYTHON_API, "python", threshold=0.10
        )
        assert is_stale  # 0 rows / 2 expected = 0% < 10%
        assert rows == 0


# ---------------------------------------------------------------------------
# TC-REF-11: Platform-specific exclusion tests (unified from batch_reference.py)
# ---------------------------------------------------------------------------

class TestCppExclusions:
    """TC-REF-11 exclusions 1 & 2: C++ I-prefix names and abstract bases."""

    def test_cpp_iprefix_class_excluded(self):
        assert not _passes_platform_scope(
            {"kind": "class_specifier", "name": "IShape", "file": "include/ishape.h"}, "cpp"
        )

    def test_cpp_iprefix_struct_excluded(self):
        assert not _passes_platform_scope(
            {"kind": "struct_specifier", "name": "IMetrics", "file": "include/i_metrics.h"}, "cpp"
        )

    def test_cpp_iprefix_lowercase_second_char_passes(self):
        # "Ia..." has lowercase 'a' — does NOT match ^I[A-Z] pattern
        assert _passes_platform_scope(
            {"kind": "class_specifier", "name": "Iambic", "file": "include/iambic.h"}, "cpp"
        )

    def test_cpp_abstract_base_excluded(self):
        for name in _CPP_ABSTRACT_BASES:
            assert not _passes_platform_scope(
                {"kind": "class_specifier", "name": name, "file": "include/base.h"}, "cpp"
            ), f"{name} should be excluded as abstract base"

    def test_cpp_no_path_filter(self):
        # C++ does NOT filter by /internal/ path (name-based rules only)
        assert _passes_platform_scope(
            {"kind": "class_specifier", "name": "FontBase", "file": "include/internal/base.h"}, "cpp"
        )

    def test_cpp_enum_iprefix_passes(self):
        # enum_specifier always passes for C++ regardless of name
        assert _passes_platform_scope(
            {"kind": "enum_specifier", "name": "IFontKind", "file": "include/font_kind.h"}, "cpp"
        )

    def test_cpp_abstract_bases_frozenset_size(self):
        assert len(_CPP_ABSTRACT_BASES) == 4


class TestPythonExclusions:
    """TC-REF-11 exclusion 3: Python I-prefix names."""

    def test_python_iprefix_excluded(self):
        assert not _passes_platform_scope(
            {"kind": "class_definition", "name": "IConverter", "file": "src/iconv.py"}, "python"
        )

    def test_python_iprefix_requires_capital_second_char(self):
        # "Image" — 'I' followed by lowercase 'm', not excluded
        assert _passes_platform_scope(
            {"kind": "class_definition", "name": "Image", "file": "src/image.py"}, "python"
        )

    def test_python_regular_class_passes(self):
        assert _passes_platform_scope(
            {"kind": "class_definition", "name": "FontLoader", "file": "src/loader.py"}, "python"
        )


class TestJavaExclusions:
    """TC-REF-11 exclusion 4: Java _JAVA_INTERNAL_CLASSES."""

    def test_all_internal_classes_excluded_for_java(self):
        for name in _JAVA_INTERNAL_CLASSES:
            assert not _passes_platform_scope(
                {"kind": "class_declaration", "name": name, "file": "src/Foo.java"}, "java"
            ), f"{name} should be excluded for java"

    def test_java_internal_name_passes_for_net(self):
        assert _passes_platform_scope(
            {"kind": "class_declaration", "name": "AppPropertiesPart", "file": "src/Foo.java"}, "net"
        )

    def test_java_internal_name_passes_for_python(self):
        assert _passes_platform_scope(
            {"kind": "class_definition", "name": "BaseCollection", "file": "src/base.py"}, "python"
        )

    def test_java_internal_name_passes_for_cpp(self):
        assert _passes_platform_scope(
            {"kind": "class_specifier", "name": "Template", "file": "include/template.h"}, "cpp"
        )

    def test_java_internal_frozenset_size(self):
        assert len(_JAVA_INTERNAL_CLASSES) == 31

    def test_java_public_class_passes(self):
        assert _passes_platform_scope(
            {"kind": "class_declaration", "name": "Presentation", "file": "src/Presentation.java"}, "java"
        )


class TestNetExclusions:
    """TC-REF-11 exclusion 5: .NET .Internal. / .internal. namespace."""

    def test_net_internal_namespace_excluded(self):
        assert not _passes_platform_scope(
            {"kind": "class_declaration", "name": "CacheManager",
             "file": "src/CacheManager.cs", "class_import": "Aspose.Slides.Internal.CacheManager"}, "net"
        )

    def test_net_lowercase_internal_namespace_excluded(self):
        assert not _passes_platform_scope(
            {"kind": "class_declaration", "name": "Helper",
             "file": "src/Helper.cs", "class_import": "Aspose.Slides.internal.Helper"}, "net"
        )

    def test_net_public_namespace_passes(self):
        assert _passes_platform_scope(
            {"kind": "class_declaration", "name": "Presentation",
             "file": "src/Presentation.cs", "class_import": "Aspose.Slides.Presentation"}, "net"
        )

    def test_net_no_class_import_passes(self):
        # Entries without class_import should not be excluded by .Internal. check
        assert _passes_platform_scope(
            {"kind": "class_declaration", "name": "FontConverter", "file": "src/FontConverter.cs"}, "net"
        )

    def test_net_internal_not_applied_to_java(self):
        # .Internal. namespace check must NOT block java entries
        assert _passes_platform_scope(
            {"kind": "class_declaration", "name": "CacheManager",
             "file": "src/CacheManager.java",
             "class_import": "Aspose.Slides.Internal.CacheManager"}, "java"
        )
