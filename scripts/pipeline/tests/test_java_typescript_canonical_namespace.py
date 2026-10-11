"""Tests for the Java and TypeScript canonical_namespace extraction branches
(TC-DUPIDX-06, 2026-08-12, ST-059).

Java: canonical_namespace now mirrors class_package (already-extracted data,
just never surfaced under the field name _assign_namespace_slug_suffixes()
reads). TypeScript: canonical_namespace is derived from file location relative
to pkg_root, mirroring the existing Python branch -- TypeScript previously had
no namespace-equivalent field of any kind.
"""
# sys.path is set by tests/conftest.py — no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

def test_java_canonical_namespace_mirrors_class_package(tmp_path):
    pkg_root = tmp_path / "src"
    pkg_root.mkdir(parents=True)
    (pkg_root / "com/aspose/cells_foss").mkdir(parents=True)
    (pkg_root / "com/aspose/cells_foss/DiagnosticSeverity.java").write_text(
        "package com.aspose.cells_foss;\n"
        "public enum DiagnosticSeverity { WARNING, FATAL }\n",
        encoding="utf-8",
    )
    (pkg_root / "com/aspose/cells_foss/core").mkdir(parents=True)
    (pkg_root / "com/aspose/cells_foss/core/DiagnosticSeverity.java").write_text(
        "package com.aspose.cells_foss.core;\n"
        "public enum DiagnosticSeverity { WARNING, FATAL }\n",
        encoding="utf-8",
    )
    parser = scout.get_parser("java")
    all_classes, *_ = extract_api_surface(parser, "java", pkg_root, tmp_path, "fake")
    diag = [c for c in all_classes if c["name"] == "DiagnosticSeverity"]
    assert len(diag) == 2
    namespaces = {c["canonical_namespace"] for c in diag}
    assert namespaces == {"com.aspose.cells_foss", "com.aspose.cells_foss.core"}
    for c in diag:
        assert c["canonical_namespace"] == c["class_package"]


def test_java_canonical_namespace_absent_without_package(tmp_path):
    pkg_root = tmp_path / "src"
    pkg_root.mkdir(parents=True)
    (pkg_root / "Foo.java").write_text("public class Foo {}\n", encoding="utf-8")
    parser = scout.get_parser("java")
    classes, *_ = extract_api_surface(parser, "java", pkg_root, tmp_path, "fake")
    foo = next(c for c in classes if c["name"] == "Foo")
    assert "canonical_namespace" not in foo
    assert foo["class_import"] == "Foo"


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------

def test_typescript_canonical_namespace_derived_from_file_path(tmp_path):
    pkg_root = tmp_path / "src"
    parser = scout.get_parser("typescript")
    classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
    # sanity: no files yet, empty extraction
    assert classes == []

    (pkg_root).mkdir(parents=True, exist_ok=True)
    (pkg_root / "types.ts").write_text(
        "export type CellValue = string | number | boolean;\n", encoding="utf-8",
    )
    (pkg_root / "util.ts").write_text(
        "export type CellValue = string | number | boolean;\n", encoding="utf-8",
    )
    classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
    cell_values = [c for c in classes if c["name"] == "CellValue"]
    assert len(cell_values) == 2
    namespaces = {c["canonical_namespace"] for c in cell_values}
    assert namespaces == {"types", "util"}
    for c in cell_values:
        assert c["class_import"] == f"{c['canonical_namespace']}.CellValue"


def test_typescript_canonical_namespace_nested_directory_dot_joined(tmp_path):
    pkg_root = tmp_path / "src"
    pkg_root.mkdir(parents=True)
    nested = pkg_root / "aspose_cells"
    nested.mkdir()
    (nested / "comment.ts").write_text(
        "export class Comment { constructor() {} }\n", encoding="utf-8",
    )
    parser = scout.get_parser("typescript")
    classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
    comment = next(c for c in classes if c["name"] == "Comment")
    assert comment["canonical_namespace"] == "aspose_cells.comment"


def test_typescript_index_file_drops_trailing_index_segment(tmp_path):
    pkg_root = tmp_path / "src"
    pkg_root.mkdir(parents=True)
    nested = pkg_root / "aspose_cells"
    nested.mkdir()
    (nested / "index.ts").write_text(
        "export class Workbook { constructor() {} }\n", encoding="utf-8",
    )
    parser = scout.get_parser("typescript")
    classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
    workbook = next(c for c in classes if c["name"] == "Workbook")
    assert workbook["canonical_namespace"] == "aspose_cells"
