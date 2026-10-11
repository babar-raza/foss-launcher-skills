"""SEO-SCHEMA-A-AUDIT-STALE-ENTRIES: audit_schema_a.py unit tests.

Covers the prospective-vs-drifted classification split that turned out to be
the load-bearing part of this task: a naive "does the title match anything
on disk" check alone would have flagged 100% of every Schema A family's
entries as orphaned, including the 6 stub-tier families (cad, imaging, ocr,
psd, tasks, zip) that have zero launched content by design -- for those,
"no match" is expected prospective demand signal, not staleness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.audit_schema_a as audit  # noqa: E402


def test_extract_title_reads_frontmatter_title():
    text = "---\ntitle: My Real Title\ndescription: x\n---\nBody text\n"
    assert audit._extract_title(text) == "My Real Title"


def test_extract_title_returns_none_without_frontmatter():
    assert audit._extract_title("Just plain text, no frontmatter") is None


def test_extract_title_returns_none_on_malformed_yaml():
    text = "---\ntitle: [unterminated\n---\nBody\n"
    assert audit._extract_title(text) is None


def test_build_real_title_index_indexes_across_sites(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    (tmp_path / "kb.aspose.org" / "en" / "pdf").mkdir(parents=True)
    (tmp_path / "kb.aspose.org" / "en" / "pdf" / "page.md").write_text(
        "---\ntitle: How To Convert PDF\n---\nBody", encoding="utf-8"
    )
    (tmp_path / "docs.aspose.org" / "en" / "pdf" / "net").mkdir(parents=True)
    (tmp_path / "docs.aspose.org" / "en" / "pdf" / "net" / "_index.md").write_text(
        "---\ntitle: Developer Guide\n---\nBody", encoding="utf-8"
    )

    index = audit.build_real_title_index(content_root=tmp_path)
    assert "How To Convert PDF" in index
    assert "Developer Guide" in index


def test_build_real_title_index_skips_locale_variant_files(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    (tmp_path / "blog.aspose.org" / "pdf" / "net").mkdir(parents=True)
    (tmp_path / "blog.aspose.org" / "pdf" / "net" / "index.md").write_text(
        "---\ntitle: English Post\n---\nBody", encoding="utf-8"
    )
    (tmp_path / "blog.aspose.org" / "pdf" / "net" / "index.ar.md").write_text(
        "---\ntitle: Arabic Post\n---\nBody", encoding="utf-8"
    )

    index = audit.build_real_title_index(content_root=tmp_path)
    assert "English Post" in index
    assert "Arabic Post" not in index


def test_family_has_launched_content_true_when_kb_dir_has_pages(tmp_path):
    (tmp_path / "kb.aspose.org" / "en" / "pdf").mkdir(parents=True)
    (tmp_path / "kb.aspose.org" / "en" / "pdf" / "page.md").write_text("---\ntitle: X\n---\n", encoding="utf-8")
    assert audit.family_has_launched_content("pdf", content_root=tmp_path) is True


def test_family_has_launched_content_false_for_products_only_family(tmp_path):
    # products.aspose.org always has a family landing page even for stub-tier
    # families -- must not count as "launched content" on its own.
    (tmp_path / "products.aspose.org" / "en" / "cad").mkdir(parents=True)
    (tmp_path / "products.aspose.org" / "en" / "cad" / "_index.md").write_text("---\ntitle: X\n---\n", encoding="utf-8")
    assert audit.family_has_launched_content("cad", content_root=tmp_path) is False


def test_audit_family_file_source_path_present_and_exists_is_live(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    (tmp_path / "real.md").write_text("x", encoding="utf-8")

    family_file = tmp_path / "pdf.json"
    family_file.write_text(json.dumps([
        {"pageTitle": "Anything", "sourcePath": "real.md", "keywords": ["a"]}
    ]), encoding="utf-8")

    result = audit.audit_family_file(family_file, real_titles={})
    assert result["live_entries"] == 1
    assert result["orphan_candidates"] == 0


def test_audit_family_file_source_path_present_but_missing_is_orphan(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)

    family_file = tmp_path / "pdf.json"
    family_file.write_text(json.dumps([
        {"pageTitle": "Anything", "sourcePath": "does/not/exist.md", "keywords": ["a"]}
    ]), encoding="utf-8")

    result = audit.audit_family_file(family_file, real_titles={})
    assert result["orphan_candidates"] == 1
    assert result["orphans"][0]["reason"] == "sourcePath_missing_on_disk"


def test_audit_family_file_classifies_prospective_vs_drifted(tmp_path, monkeypatch):
    family_file = tmp_path / "widgets.json"
    family_file.write_text(json.dumps([
        {"pageTitle": "Old Title 1", "keywords": ["a"]},
        {"pageTitle": "Old Title 2", "keywords": ["b"]},
    ]), encoding="utf-8")

    monkeypatch.setattr(audit, "family_has_launched_content", lambda family, content_root=None: False)
    result = audit.audit_family_file(family_file, real_titles={})
    assert result["orphan_classification"] == "prospective_no_launched_content"
    assert result["orphan_candidates"] == 2

    monkeypatch.setattr(audit, "family_has_launched_content", lambda family, content_root=None: True)
    result = audit.audit_family_file(family_file, real_titles={})
    assert result["orphan_classification"] == "drifted_title_mismatch"
    assert result["orphan_candidates"] == 2


def test_audit_family_file_no_orphans_is_n_a(tmp_path, monkeypatch):
    family_file = tmp_path / "widgets.json"
    family_file.write_text(json.dumps([{"pageTitle": "Live Title", "keywords": ["a"]}]), encoding="utf-8")
    monkeypatch.setattr(audit, "family_has_launched_content", lambda family, content_root=None: True)

    result = audit.audit_family_file(family_file, real_titles={"Live Title": ["some/path.md"]})
    assert result["orphan_candidates"] == 0
    assert result["orphan_classification"] == "n/a"
