"""Tests for scripts/verify.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import verify


def _make_pef():
    """Return a sample PEF dict for testing."""
    return {
        "schema_version": 1,
        "family": "words",
        "platform": "python",
        "display_name": "Aspose.Words",
        "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": "abc123",
        "provenance_summary": {"dual": 2, "dual_fuzzy": 0, "scout_only": 1, "external_only": 0, "total": 3, "dual_pct": 66.7},
        "api_confidence": "high",
        "claims": [
            {"claim_id": "CLM-001", "kind": "api_class", "text": "Document class", "provenance": "dual"},
            {"claim_id": "CLM-002", "kind": "api_method", "text": "Document.load", "provenance": "dual"},
            {"claim_id": "CLM-003", "kind": "api_method", "text": "Document.save", "provenance": "scout_only"},
        ],
        "api_surface": [
            {"name": "Document", "kind": "class", "methods": [
                {"name": "load"}, {"name": "save"}, {"name": "convert"}
            ]},
        ],
        "formats": [
            {"format": "DOCX", "can_import": True, "can_export": True},
            {"format": "PDF", "can_import": False, "can_export": True},
        ],
        "forbidden_claims": ["supports Workbook.protect"],
        "class_graph": [],
        "coverage_matrix": [],
        "constants": [],
        "limitations": [],
        "install": {"command": "pip install aspose-words-foss", "version": "", "raw_md": ""},
        "snippets": [],
        "index_metadata": {},
    }


def test_extract_citations():
    content = """
Some text
<!-- evidence: claim_id=CLM-001 source=readme.md confidence=0.9 -->
More text
<!-- evidence: claim_id=CLM-002 -->
"""
    citations = verify._extract_citations(content)
    assert len(citations) == 2
    assert citations[0]["claim_id"] == "CLM-001"
    assert citations[0]["source"] == "readme.md"
    assert citations[1]["claim_id"] == "CLM-002"


def test_extract_api_references():
    content = """
Use the `Document.load(` method to load files.

```python
from aspose.words import Document

doc = Document("input.docx")
doc.save("output.docx")
doc.convert("pdf", "out.pdf")
```
"""
    refs = verify._extract_api_references(content)
    assert "Document" in refs
    assert "save" in refs
    assert "convert" in refs


def test_extract_format_claims():
    content = """
Supports **DOCX** format for import and export.
Also exports to PDF.

```python
# code block with XLSX should be ignored
```
"""
    formats = verify._extract_format_claims(content)
    assert "DOCX" in formats
    assert "PDF" in formats


def test_verify_pass_when_all_grounded(tmp_path, monkeypatch):
    pef = _make_pef()
    monkeypatch.setattr(verify, "EVIDENCE_ROOT", tmp_path / "evidence")

    # Create evidence dir for report writing
    (tmp_path / "evidence" / "words" / "python" / "verification").mkdir(parents=True)

    content = """---
title: Test
---
## Overview
<!-- evidence: claim_id=CLM-001 -->

```python
from aspose.words import Document
doc = Document("input.docx")
doc.load("file.docx")
```
"""
    content_file = tmp_path / "test.md"
    content_file.write_text(content, encoding="utf-8")

    report = verify.verify_page(content_file, pef)
    assert report["result"] in ("PASS", "WARN")
    assert report["citations"]["valid"] == 1
    assert report["citations"]["orphaned"] == 0


def test_verify_warn_on_orphaned_citation(tmp_path, monkeypatch):
    pef = _make_pef()
    monkeypatch.setattr(verify, "EVIDENCE_ROOT", tmp_path / "evidence")
    (tmp_path / "evidence" / "words" / "python" / "verification").mkdir(parents=True)

    content = """---
title: Test
---
<!-- evidence: claim_id=CLM-001 -->
<!-- evidence: claim_id=NONEXISTENT-999 -->
Use `Document.load(` method.
"""
    content_file = tmp_path / "test.md"
    content_file.write_text(content, encoding="utf-8")

    report = verify.verify_page(content_file, pef)
    assert report["citations"]["orphaned"] == 1
    assert "NONEXISTENT-999" in report["citations"]["orphaned_ids"]
    assert any(i["type"] == "orphaned_citation" for i in report["issues"])


def test_verify_fail_on_forbidden_claim(tmp_path, monkeypatch):
    pef = _make_pef()
    monkeypatch.setattr(verify, "EVIDENCE_ROOT", tmp_path / "evidence")
    (tmp_path / "evidence" / "words" / "python" / "verification").mkdir(parents=True)

    content = """---
title: Test
---
The library supports Workbook.protect for password protection.
"""
    content_file = tmp_path / "test.md"
    content_file.write_text(content, encoding="utf-8")

    report = verify.verify_page(content_file, pef)
    assert report["result"] == "FAIL"
    assert len(report["forbidden_violations"]) > 0


def test_check_forbidden():
    violations = verify._check_forbidden(
        "This supports Workbook.protect and more",
        ["supports Workbook.protect"]
    )
    assert len(violations) == 1


def test_resolve_family_platform():
    f, p = verify._resolve_family_platform(
        Path("output/content/docs.aspose.org/en/words/python/intro.md")
    )
    assert f == "words"
    assert p == "python"


def test_verify_produces_report_file(tmp_path, monkeypatch):
    pef = _make_pef()
    monkeypatch.setattr(verify, "EVIDENCE_ROOT", tmp_path / "evidence")

    content = "## Test\n<!-- evidence: claim_id=CLM-001 -->\n"
    content_file = tmp_path / "sample.md"
    content_file.write_text(content, encoding="utf-8")

    report = verify.verify_page(content_file, pef)

    verify_dir = tmp_path / "evidence" / "words" / "python" / "verification"
    assert verify_dir.exists()
    report_files = list(verify_dir.glob("sample-*.json"))
    assert len(report_files) == 1
