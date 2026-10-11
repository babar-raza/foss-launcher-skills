"""Unit tests for audit_family_subtitles.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_DIAG = Path(__file__).resolve().parent.parent / "commands" / "diagnostics"
if str(_DIAG) not in sys.path:
    sys.path.insert(0, str(_DIAG))

from audit_family_subtitles import audit_subtitle, _SUBTITLE_MAX  # noqa: E402


def _write_index(tmp: Path, content: str) -> Path:
    """Write a family _index.md in a temp structure and return its path."""
    p = tmp / "_index.md"
    p.write_text(content, encoding="utf-8")
    return p


class TestAuditSubtitle:
    def test_missing_file(self, tmp_path):
        p = tmp_path / "nonexistent" / "_index.md"
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "FAIL"
        assert any(i["code"] == "FILE_MISSING" for i in result["issues"])

    def test_missing_subtitle(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Font FOSS\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "FAIL"
        assert any(i["code"] == "MISSING" for i in result["issues"])

    def test_empty_subtitle(self, tmp_path):
        p = _write_index(tmp_path, '---\ntitle: Aspose.Font FOSS\nsubtitle: ""\n---\nBody\n')
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "FAIL"
        assert any(i["code"] == "EMPTY" for i in result["issues"])

    def test_whitespace_subtitle(self, tmp_path):
        p = _write_index(tmp_path, '---\ntitle: Aspose.Font FOSS\nsubtitle: "   "\n---\nBody\n')
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "FAIL"
        assert any(i["code"] == "EMPTY" for i in result["issues"])

    def test_valid_subtitle(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Font FOSS\nsubtitle: Font loading and conversion\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "OK"
        assert result["issues"] == []
        assert result["subtitle"] == "Font loading and conversion"
        assert result["chars"] == 27

    def test_exactly_max_length(self, tmp_path):
        sub = "A" * _SUBTITLE_MAX
        p = _write_index(tmp_path, f"---\ntitle: Aspose.Font FOSS\nsubtitle: {sub}\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "OK"
        assert result["chars"] == _SUBTITLE_MAX

    def test_over_max_length(self, tmp_path):
        sub = "A" * (_SUBTITLE_MAX + 5)
        p = _write_index(tmp_path, f"---\ntitle: Aspose.Font FOSS\nsubtitle: {sub}\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "FAIL"
        assert any(i["code"] == "OVER_LENGTH" for i in result["issues"])

    def test_platform_specific_python(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Font FOSS\nsubtitle: Open-source Python library for fonts\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "WARN"
        assert any(i["code"] == "PLATFORM_SPECIFIC" for i in result["issues"])

    def test_platform_specific_java(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Cells FOSS\nsubtitle: Java spreadsheet library\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "cells")
        assert result["severity"] == "WARN"
        assert any(i["code"] == "PLATFORM_SPECIFIC" for i in result["issues"])

    def test_platform_specific_dotnet(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Words FOSS\nsubtitle: .NET word processing\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "words")
        assert result["severity"] == "WARN"
        assert any(i["code"] == "PLATFORM_SPECIFIC" for i in result["issues"])

    def test_no_platform_term_false_positive(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Font FOSS\nsubtitle: Open-source font loading, rendering, and conversion\n---\nBody\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "OK"
        assert not any(i["code"] == "PLATFORM_SPECIFIC" for i in result["issues"])

    def test_parse_error(self, tmp_path):
        p = _write_index(tmp_path, "No frontmatter here\n")
        result = audit_subtitle(p, "docs.aspose.org", "font")
        assert result["severity"] == "FAIL"
        assert any(i["code"] == "PARSE_ERROR" for i in result["issues"])

    def test_protected_page_only_subtitle_checked(self, tmp_path):
        p = _write_index(tmp_path, "---\ntitle: Aspose.Font FOSS\nsubtitle: Good subtitle here\nprovenance:\n  auto_updatable: false\n---\nBody\n")
        result = audit_subtitle(p, "reference.aspose.org", "font")
        assert result["severity"] == "OK"


class TestAuditLiveRepo:
    """Run audit against the actual repo content — integration test."""

    def test_all_24_families_pass(self):
        from audit_family_subtitles import run_audit
        results = run_audit()
        fails = [r for r in results if r["severity"] == "FAIL"]
        fail_names = [r["site"] + "/" + r["family"] for r in fails]
        assert fails == [], f"FAIL entries: {fail_names}"
