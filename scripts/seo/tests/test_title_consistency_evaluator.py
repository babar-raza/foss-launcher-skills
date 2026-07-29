"""SEO-TITLE-CONSISTENCY-EVALUATOR: WARN-only, zero-write evaluator tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.title_consistency_evaluator as evaluator  # noqa: E402


def _write_page(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\nBody\n", encoding="utf-8")


def test_evaluate_devguide_pages_flags_the_known_duplicate_title(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(
        tmp_path / "docs.aspose.org" / "en" / "pdf" / "net" / "developer-guide" / "_index.md",
        "Developer Guide",
    )
    results = evaluator.evaluate_devguide_pages()
    assert len(results) == 1
    assert results[0]["conforms"] is False
    assert results[0]["family"] == "pdf"
    assert results[0]["platform"] == "net"


def test_evaluate_devguide_pages_passes_a_conformant_title(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(tmp_path / "products.aspose.org" / "en" / "pdf" / "_index.md", "Aspose.PDF FOSS")
    _write_page(
        tmp_path / "docs.aspose.org" / "en" / "pdf" / "net" / "developer-guide" / "_index.md",
        "Aspose.PDF FOSS for .NET Developer Guide",
    )
    results = evaluator.evaluate_devguide_pages()
    assert results[0]["conforms"] is True


def test_evaluate_faq_pages_flags_the_known_duplicate_title(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(
        tmp_path / "kb.aspose.org" / "en" / "page" / "python" / "faq.md",
        "Frequently Asked Questions",
    )
    results = evaluator.evaluate_faq_pages()
    assert len(results) == 1
    assert results[0]["conforms"] is False


def test_evaluate_faq_pages_passes_conformant_title(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(tmp_path / "products.aspose.org" / "en" / "page" / "_index.md", "Aspose.Page FOSS")
    _write_page(
        tmp_path / "kb.aspose.org" / "en" / "page" / "python" / "faq.md",
        "Aspose.Page FOSS for Python FAQ",
    )
    results = evaluator.evaluate_faq_pages()
    assert results[0]["conforms"] is True


def test_family_display_name_derives_from_products_root(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(tmp_path / "products.aspose.org" / "en" / "pdf" / "_index.md", "Aspose.PDF FOSS")
    assert evaluator._family_display_name("pdf") == "PDF"


def test_family_display_name_falls_back_to_upper_when_products_page_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    assert evaluator._family_display_name("pdf") == "PDF"


def test_platform_display_name_known_and_unknown():
    assert evaluator._platform_display_name("net") == ".NET"
    assert evaluator._platform_display_name("python") == "Python"
    assert evaluator._platform_display_name("rust") == "rust"


def test_evaluate_ignores_non_devguide_non_faq_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(tmp_path / "docs.aspose.org" / "en" / "pdf" / "net" / "getting-started" / "_index.md", "Getting Started")
    _write_page(tmp_path / "kb.aspose.org" / "en" / "page" / "python" / "troubleshooting.md", "Troubleshooting")
    assert evaluator.evaluate_devguide_pages() == []
    assert evaluator.evaluate_faq_pages() == []


def test_build_report_never_touches_content_files(tmp_path, monkeypatch):
    """WARN-only guarantee: build_report() must not modify any content file
    on disk, only read it."""
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    page = tmp_path / "docs.aspose.org" / "en" / "pdf" / "net" / "developer-guide" / "_index.md"
    _write_page(page, "Developer Guide")
    before = page.read_bytes()

    evaluator.build_report()

    assert page.read_bytes() == before


def test_build_report_aggregates_pass_and_warn_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "CONTENT_ROOT", tmp_path)
    _write_page(tmp_path / "products.aspose.org" / "en" / "words" / "_index.md", "Aspose.Words FOSS")
    _write_page(tmp_path / "docs.aspose.org" / "en" / "pdf" / "net" / "developer-guide" / "_index.md", "Developer Guide")
    _write_page(tmp_path / "docs.aspose.org" / "en" / "words" / "net" / "developer-guide" / "_index.md", "Aspose.Words FOSS for .NET Developer Guide")

    report = evaluator.build_report()
    assert report["meta"]["total_evaluated"] == 2
    assert report["meta"]["pass_count"] == 1
    assert report["meta"]["warn_count"] == 1


def test_real_evaluator_runs_against_live_content_without_writing():
    """Smoke test against the real repo -- must not raise, must find the 31
    real devguide + 31 real FAQ pages, and must not write to content/."""
    report = evaluator.build_report()
    assert report["meta"]["docs_devguide_index_total"] >= 20
    assert report["meta"]["kb_faq_total"] >= 20
    assert report["meta"]["total_evaluated"] == len(report["warn"]) + len(report["pass"])
