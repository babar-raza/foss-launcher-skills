"""SEO-KEYWORDS-FRONTMATTER-GROUNDING: frontmatter_grounding_audit.py tests."""
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

import seo.pipeline.frontmatter_grounding_audit as audit  # noqa: E402


def _write_page(root: Path, rel: str, fm: dict) -> None:
    import yaml
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump(fm) + "---\nBody\n", encoding="utf-8")


def test_audit_kb_pages_skips_index_files(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "_url_map_cache", {})
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/_index.md", {"title": "Index"})
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/faq.md", {"title": "FAQ", "keywords": ["a", "b"]})

    results = audit.audit_kb_pages()
    assert len(results) == 1
    assert results[0]["path"].endswith("faq.md")


def test_audit_kb_pages_reports_existing_keyword_count(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "_url_map_cache", {})
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/faq.md", {
        "title": "FAQ", "keywords": ["a", "b", "c", "d", "e"],
    })

    results = audit.audit_kb_pages()
    assert results[0]["existing_keyword_count"] == 5
    assert results[0]["meets_min_5_count"] is True


def test_audit_kb_pages_uses_grounding_module(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "_url_map_cache", {})
    monkeypatch.setattr(
        audit, "ground_keywords_for_page",
        lambda **kw: {"keywords": ["x", "y"], "keyword_source": "derived"},
    )
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/faq.md", {"title": "FAQ", "description": "d"})

    results = audit.audit_kb_pages()
    assert results[0]["grounded_keyword_source"] == "derived"
    assert results[0]["grounded_keyword_count"] == 2


def test_build_report_aggregates_by_source(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "_url_map_cache", {})
    monkeypatch.setattr(
        audit, "ground_keywords_for_page",
        lambda **kw: {"keywords": [], "keyword_source": "none"},
    )
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/a.md", {"title": "A"})
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/b.md", {"title": "B"})

    report = audit.build_report()
    assert report["meta"]["total_kb_pages"] == 2
    assert report["meta"]["by_grounded_source"] == {"none": 2}


def test_audit_never_writes_to_content_files(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(audit, "_url_map_cache", {})
    page = tmp_path / "kb.aspose.org" / "en" / "pdf" / "net" / "faq.md"
    _write_page(tmp_path, "kb.aspose.org/en/pdf/net/faq.md", {"title": "FAQ"})
    before = page.read_bytes()

    audit.build_report()

    assert page.read_bytes() == before


def test_real_audit_runs_against_live_content():
    """Smoke test against the real repo -- must not raise."""
    report = audit.build_report()
    assert report["meta"]["total_kb_pages"] > 0
    assert sum(report["meta"]["by_grounded_source"].values()) == report["meta"]["total_kb_pages"]
