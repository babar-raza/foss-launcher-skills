"""Regression tests for prose_truth.py's directional format-claim resolution
(ST-023, 2026-07-30).

Bug (found via the 2026-07-14 pdf/go truth audit,
reports/audit/pdf-go-truth-2026-07-14.md, blog/pdf-document-management-go
FAIL): the evaluator flagged "Aspose.PDF FOSS for Go now exports PDF
documents to HTML..." as a prose_truth FAIL -- "Claims PDF export but
knowledge shows import-only". This is a false positive: the sentence
describes exporting FROM PDF TO HTML (PDF is the SOURCE, HTML is the
claimed export TARGET), not a claim that PDF itself is an export target.

Root cause: the old `_FORMAT_CLAIM_RE`-only matching grabbed whichever short
token sat directly before "format"/"file"/"document" (here, "PDF" in
"exports PDF documents"), then separately checked whether the literal
substring "export"/"import" appeared ANYWHERE on the line to guess a
direction -- with no attempt to resolve which of the (potentially several)
format-like tokens on the line was actually the one the sentence claims a
capability for. Fix: `_DIRECTIONAL_CLAIM_RE` / `_HYPHEN_TO_RE` resolve the
real "<verb> ... to/into/from <FORMAT>" (or "X-to-Y") clause first, using
the page's own formats.json-backed `format_support` dict (not a hardcoded
allowlist) to confirm the candidate token is a real format for this
product before ever treating it as a claim.
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from content_eval.evaluators import prose_truth as _pt
from content_eval.models import Page


def _make_page(content: str, filepath: str = "content/blog.aspose.org/pdf/go/test/index.md") -> Page:
    """Create a Page from markdown content string (mirrors test_evaluators.py's helper)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


def _write_formats(tmp_path, family, platform, entries):
    merged_dir = tmp_path / family / platform / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "formats.json").write_text(json.dumps(entries), encoding="utf-8")


@pytest.fixture
def evaluator():
    return _pt.ProseTruthEvaluator()


class TestDirectionalClaimRegex:
    """Unit tests for the regex/split logic in isolation (no Page/knowledge needed)."""

    def test_export_to_clause_captures_target_not_source(self):
        """'exports PDF documents to HTML' must resolve fmt=HTML, prep=to --
        not fmt=PDF (the old nearest-token bug)."""
        s = "Aspose.PDF FOSS for Go now exports PDF documents to HTML for web publishing."
        matches = list(_pt._DIRECTIONAL_CLAIM_RE.finditer(s))
        assert matches, "expected a directional match on the export-to clause"
        m = matches[0]
        assert m.group("fmt").lower() == "html"
        assert m.group("prep").lower() == "to"
        # The source token "PDF" must fall strictly before the "to" preposition,
        # so it can be correctly shadowed as the acted-upon document, not an
        # independent claim.
        assert m.start() < m.start("prep")

    def test_converts_x_to_y_resolves_target(self):
        s = "The library converts DOCX documents to PDF."
        m = _pt._DIRECTIONAL_CLAIM_RE.search(s)
        assert m is not None
        assert m.group("prep").lower() == "to"
        assert m.group("fmt").lower() == "pdf"

    def test_imports_from_clause_resolves_source(self):
        s = "The converter imports data from XML files for further processing."
        m = _pt._DIRECTIONAL_CLAIM_RE.search(s)
        assert m is not None
        assert m.group("prep").lower() == "from"
        assert m.group("fmt").lower() == "xml"

    def test_hyphenated_x_to_y_conversion(self):
        s = "Aspose.Cells FOSS supports XLS-to-CSV conversion."
        m = _pt._HYPHEN_TO_RE.search(s)
        assert m is not None
        assert m.group(1).lower() == "xls"
        assert m.group(2).lower() == "csv"

    def test_reads_and_writes_has_no_directional_preposition(self):
        """'reads Y and writes X' has no to/into/from clause -- the new
        directional regex must not fire (falls through to the old,
        unaffected nearest-token + verb-substring logic)."""
        s = "The library reads DOCX files and writes PDF files."
        assert _pt._DIRECTIONAL_CLAIM_RE.search(s) is None


class TestProseTruthDirectionalityIntegration:
    """Full evaluate() tests: real Page + real formats.json on disk, via the
    prose_truth.configure() testing seam (AGENTS.md §16) rather than raw
    monkeypatch.setattr on KNOWLEDGE_ROOT (see test_format_truth_functional_flag.py
    for the older, grandfathered monkeypatch-based precedent for format_truth.py --
    new test files use the seam instead)."""

    @pytest.fixture(autouse=True)
    def _reset_knowledge_root(self):
        yield
        _pt.configure()

    def test_pdf_export_to_html_false_positive_fixed(self, evaluator, tmp_path):
        """The EXACT literal false-positive sentence from the pdf/go truth
        audit must no longer produce a PT FAIL for PDF."""
        _pt.configure(knowledge_root=tmp_path)
        # pdf/go: PDF is import-only (its own native/source format); HTML is
        # export-only (the real, verified SaveHTML/WriteHTML capability).
        _write_formats(tmp_path, "pdf", "go", [
            {"format": "pdf", "direction": "import"},
            {"format": "html", "direction": "export"},
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Aspose.PDF FOSS for Go now exports PDF documents to HTML, exposes optional
            content layers on the page tree, and provides a facade for authoring Tagged
            PDF (accessible) documents.
        """), "content/blog.aspose.org/pdf/go/pdf-document-management-go/index.md")
        findings = evaluator.evaluate(page, None)
        pdf_fails = [
            f for f in findings
            if f.category == "PT" and "PDF" in f.message and "export" in f.message.lower()
        ]
        assert pdf_fails == [], (
            f"false-positive PDF export FAIL must not fire; got: {[f.message for f in findings]}"
        )

    def test_html_export_correctly_verified_no_finding(self, evaluator, tmp_path):
        """The HTML export claim in the same sentence IS a real, verified
        capability -- it must produce no finding either (positive control:
        this fix must not just suppress everything)."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "pdf", "go", [
            {"format": "pdf", "direction": "import"},
            {"format": "html", "direction": "export"},
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Aspose.PDF FOSS for Go now exports PDF documents to HTML for web publishing.
        """), "content/blog.aspose.org/pdf/go/pdf-document-management-go/index.md")
        findings = evaluator.evaluate(page, None)
        html_findings = [f for f in findings if f.category == "PT" and "HTML" in f.message]
        assert html_findings == [], f"HTML export claim is genuinely verified; got: {html_findings}"

    def test_true_violation_still_fails_export_to_target(self, evaluator, tmp_path):
        """Must not become permissive: a genuinely FALSE claim -- exporting
        to a format that is import-only -- must still FAIL."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "cells", "net", [
            {"format": "xlsx", "direction": "import"},  # NOT export-capable
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            The library now converts workbook data to XLSX for downstream reporting.
        """), "content/blog.aspose.org/cells/net/test/index.md")
        findings = evaluator.evaluate(page, None)
        xlsx_fails = [
            f for f in findings
            if f.category == "PT" and "XLSX" in f.message and f.level == "FAIL"
        ]
        assert len(xlsx_fails) == 1, (
            f"expected a real XLSX export-mismatch FAIL; got: {[f.message for f in findings]}"
        )
        assert "import-only" in xlsx_fails[0].message

    def test_true_violation_still_fails_import_from_source(self, evaluator, tmp_path):
        """Symmetric true-violation control: claiming import FROM a format
        that is actually export-only must still FAIL."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "mhtml", "direction": "export"},  # NOT import-capable
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            The document builder imports content from MHTML archives before rendering.
        """), "content/blog.aspose.org/words/net/test/index.md")
        findings = evaluator.evaluate(page, None)
        mhtml_fails = [
            f for f in findings
            if f.category == "PT" and "MHTML" in f.message and f.level == "FAIL"
        ]
        assert len(mhtml_fails) == 1
        assert "export-only" in mhtml_fails[0].message

    def test_hyphenated_conversion_true_violation_fails(self, evaluator, tmp_path):
        """'X-to-Y conversion' phrasing: a genuinely false claim on either
        side must still FAIL (not just made permissive by the new pattern)."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "cells", "net", [
            {"format": "xls", "direction": "export"},   # NOT import-capable
            {"format": "csv", "direction": "import"},   # NOT export-capable
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Aspose.Cells FOSS supports XLS-to-CSV conversion for legacy spreadsheets.
        """), "content/blog.aspose.org/cells/net/test/index.md")
        findings = evaluator.evaluate(page, None)
        messages = [f.message for f in findings if f.category == "PT" and f.level == "FAIL"]
        # XLS is the SOURCE ("X" in "X-to-Y") -> claimed import, but fixture
        # says XLS is export-only.
        assert any("XLS" in msg and "import" in msg and "export-only" in msg
                   for msg in messages), (
            f"expected 'Claims XLS import but knowledge shows export-only'; got: {messages}"
        )
        # CSV is the DESTINATION ("Y" in "X-to-Y") -> claimed export, but
        # fixture says CSV is import-only.
        assert any("CSV" in msg and "export" in msg and "import-only" in msg
                   for msg in messages), (
            f"expected 'Claims CSV export but knowledge shows import-only'; got: {messages}"
        )

    def test_hyphenated_conversion_true_positive_no_finding(self, evaluator, tmp_path):
        """'X-to-Y conversion' where both directions are genuinely supported
        must produce no finding."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "cells", "net", [
            {"format": "xls", "direction": "import"},
            {"format": "csv", "direction": "export"},
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Aspose.Cells FOSS supports XLS-to-CSV conversion for legacy spreadsheets.
        """), "content/blog.aspose.org/cells/net/test/index.md")
        findings = evaluator.evaluate(page, None)
        pt_fails = [f for f in findings if f.category == "PT" and f.level == "FAIL"]
        assert pt_fails == [], f"both directions are genuinely supported; got: {pt_fails}"

    def test_reads_and_writes_phrasing_no_crash_no_false_finding(self, evaluator, tmp_path):
        """'reads Y and writes X' negative control: no to/into/from clause
        exists, so the new directional pass must not interfere -- behavior
        is identical to pre-fix (no PT format finding for either token,
        since neither literal 'export' nor 'import' substring appears)."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "docx", "direction": "import"},
            {"format": "pdf", "direction": "export"},
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            The library reads DOCX files and writes PDF files during conversion.
        """), "content/blog.aspose.org/words/net/test/index.md")
        findings = evaluator.evaluate(page, None)
        pt_fails = [f for f in findings if f.category == "PT" and f.level == "FAIL"]
        assert pt_fails == [], f"unexpected PT FAIL for reads/writes phrasing: {pt_fails}"

    def test_unrelated_to_clause_not_treated_as_format_claim(self, evaluator, tmp_path):
        """'exports data to the caller' -- 'caller' is not a real format for
        this product, so it must never be treated as a format claim (the
        allowlist here is format_support itself, not a hardcoded list)."""
        _pt.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "pdf", "go", [
            {"format": "pdf", "direction": "import"},
        ])
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            The API exports data to the caller for further processing in memory.
        """), "content/blog.aspose.org/pdf/go/test/index.md")
        findings = evaluator.evaluate(page, None)
        pt_fails = [f for f in findings if f.category == "PT" and f.level == "FAIL"]
        assert pt_fails == []
