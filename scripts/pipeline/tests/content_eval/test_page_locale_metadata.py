"""Page._infer_metadata() must correctly read family/platform for EVERY
locale, not just English.

Root cause: the locale segment (content/{site}/{locale}/{family}/{platform}/
...) was only stripped when it literally equaled "en" -- for any other
locale (ar, de, fr, ...) the locale code itself was misread as `family` and
the real family misread as `platform`. Found live 2026-08-31 while using
S-73 (manual-edit) on an Arabic 3d/typescript page: its own re-grade step
(`content_eval evaluate --files <path>`) reported "Knowledge unavailable for
ar/3d" -- family/platform were being read as ("ar", "3d") instead of the
real ("3d", "typescript"). `discover_content()` (the batch/production
grading route) only ever returns English paths, so this never affected
fleet grading -- only ad-hoc single-file locale evaluation (S-73's own
re-grade step, and any similar direct --files invocation on a locale page).
"""
from __future__ import annotations

from pathlib import Path

from content_eval.models import Page


def _write(tmp_path: Path, rel_path: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: x\n---\n\nBody.\n", encoding="utf-8")
    return p


class TestLocaleMetadataInference:
    def test_english_page_unaffected(self, tmp_path):
        p = _write(tmp_path, "content/docs.aspose.org/en/3d/typescript/developer-guide/features.md")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("en", "3d", "typescript")

    def test_arabic_page_reads_real_family_platform(self, tmp_path):
        p = _write(tmp_path, "content/docs.aspose.org/ar/3d/typescript/developer-guide/features.md")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("ar", "3d", "typescript")

    def test_german_page_reads_real_family_platform(self, tmp_path):
        p = _write(tmp_path, "content/docs.aspose.org/de/cells/net/working-with-charts.md")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("de", "cells", "net")

    def test_reference_subdomain_locale(self, tmp_path):
        p = _write(tmp_path, "content/reference.aspose.org/es/pdf/net/Document.md")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("es", "pdf", "net")

    def test_products_subdomain_family_read_correctly(self, tmp_path):
        # products pages are content/products.aspose.org/{locale}/{family}/_index.md
        # -- `platform` picks up the filename itself here (pre-existing
        # behavior for a single-segment path shape, unrelated to this fix
        # and unchanged by it); `family` is what matters and must be correct.
        p = _write(tmp_path, "content/products.aspose.org/fr/pdf/_index.md")
        page = Page.load(p)
        assert (page.locale, page.family) == ("fr", "pdf")

    def test_blog_english_omits_locale_segment(self, tmp_path):
        # blog.aspose.org is the one site whose ENGLISH path has no locale
        # directory at all: content/blog.aspose.org/{family}/{platform}/...
        p = _write(tmp_path, "content/blog.aspose.org/cells/net/test/index.md")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("en", "cells", "net")

    def test_blog_translated_keeps_locale_segment(self, tmp_path):
        # blog.aspose.org DOES carry the locale directory for translations.
        p = _write(tmp_path, "content/blog.aspose.org/ar/cells/net/test/index.md")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("ar", "cells", "net")

    def test_unrecognized_path_shape_leaves_metadata_empty(self, tmp_path):
        p = tmp_path / "README.md"
        p.write_text("---\ntitle: x\n---\n\nBody.\n", encoding="utf-8")
        page = Page.load(p)
        assert (page.locale, page.family, page.platform) == ("", "", "")
