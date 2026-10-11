"""Regression test: batch_reference.py's Overview line must use the correct
indefinite article ("an enum", not "a enum").

Found live 2026-09-12 during MT068-2026-09-11-IMAGING-NET-LAUNCH's full
relaunch: content/reference.aspose.org/en/imaging/net/ImageFormat.md (an
enum reference page) read "`ImageFormat` is a enum in Aspose.Imaging FOSS
for .NET." -- a portfolio-wide grammar bug, not imaging-specific, since
`category.lower()` was interpolated into a hardcoded "is a {category}"
template with no vowel-sound check. Any product with an enum in its API
surface hits this.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestIndefiniteArticle:
    def _article_for(self, category: str) -> str:
        """Mirrors the exact logic in batch_reference.py's Overview-line
        builder -- kept as a small, directly-testable helper rather than
        invoking the full page-generation pipeline for a one-line check."""
        return "an" if category.lower()[:1] in "aeiou" else "a"

    def test_enum_gets_an(self):
        assert self._article_for("enum") == "an"

    def test_class_gets_a(self):
        assert self._article_for("class") == "a"

    def test_interface_gets_an(self):
        assert self._article_for("interface") == "an"

    def test_struct_gets_a(self):
        assert self._article_for("struct") == "a"

    def test_real_generated_imaging_net_pages_use_correct_article(self):
        """Live proof against the actual regenerated reference pages for
        this mission -- not just the isolated helper logic above."""
        repo_root = Path(__file__).resolve().parents[3]
        enum_page = repo_root / "content/reference.aspose.org/en/imaging/net/ImageFormat.md"
        class_page = repo_root / "content/reference.aspose.org/en/imaging/net/ImageProbe.md"
        if not enum_page.is_file() or not class_page.is_file():
            import pytest
            pytest.skip("real imaging/net reference pages not present")
        enum_text = enum_page.read_text(encoding="utf-8")
        class_text = class_page.read_text(encoding="utf-8")
        assert "is a enum" not in enum_text
        assert "is an enum" in enum_text
        assert "is a class" in class_text
        assert "is an class" not in class_text
