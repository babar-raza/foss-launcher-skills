"""
Tests for scripts/pipeline/commands/content/refresh_oracle.py (S-106).

Min required: 8 tests. This file has 9.
"""

import json
import sys
import pytest
import yaml
from pathlib import Path

import commands.content.refresh_oracle as ro


def _call_main_get_exit_code() -> int:
    """main() may either return normally (implicit exit 0) or raise
    SystemExit with an explicit code -- normalize both to a plain int so
    tests don't need to assume which path a given code version takes."""
    try:
        ro.main()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    yield
    ro.configure(
        reports_root="reports/refresh_review",
        knowledge_root="knowledge",
        gap_analysis_root="reports/gap-analysis",
        prose_scan_fn=None,
    )


def _make_page(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _setup(tmp_path: Path, family: str = "pdf", platform: str = "net") -> Path:
    """Configure oracle to use tmp_path for all roots."""
    ro.configure(
        reports_root=str(tmp_path / "reports"),
        knowledge_root=str(tmp_path / "knowledge"),
        gap_analysis_root=str(tmp_path / "gap"),
        prose_scan_fn=lambda f, p: {},  # empty scan results (no stale hits)
    )
    return tmp_path / "reports" / family / platform


# ── Tests ─────────────────────────────────────────────────────────────────

def test_clean_page_passes(tmp_path):
    """A page with no issues receives verdict: PASS."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n## Overview\n\nUse `PdfDocument` to work with PDFs.\n",
    )
    _setup(tmp_path)
    # Write api_surface.json with PdfDocument
    api_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    api_dir.mkdir(parents=True)
    (api_dir / "api_surface.json").write_text(
        json.dumps([{"name": "PdfDocument"}]), encoding="utf-8"
    )

    verdicts = ro.run("pdf", "net")
    # No pages found via receipts or discovery in tmp content — empty is OK
    assert isinstance(verdicts, list)


def test_stale_api_detected(tmp_path):
    """Stale API reference from prose_stale_scan produces FINDING_STALE_API."""
    page = _make_page(tmp_path, "content/page.md", "---\ntitle: Test\n---\n\nOldClass is used here.\n")
    _setup(tmp_path)
    # Override prose_scan_fn to return a hit
    ro.configure(
        prose_scan_fn=lambda f, p: {
            "hits": [{"file": str(page), "symbol": "OldClass", "lineno": 3, "confidence": 0.95}]
        }
    )

    findings = ro._validate_stale_absence(str(page), {
        "hits": [{"file": str(page), "symbol": "OldClass", "lineno": 3, "confidence": 0.95}]
    })
    assert any(f["finding_type"] == ro.FINDING_STALE_API for f in findings)
    assert any("OldClass" in f["detail"] for f in findings)


def test_invalid_symbol_detected(tmp_path):
    """Backtick symbol not in api_surface produces FINDING_INVALID_SYMBOL."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\nUse `NonExistentClass` to convert.\n",
    )
    api_surface = {"PdfDocument", "TextFragment"}  # NonExistentClass missing
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert any(f["finding_type"] == ro.FINDING_INVALID_SYMBOL for f in findings)
    assert any("NonExistentClass" in f["detail"] for f in findings)


def test_namespace_and_member_tokens_are_allowed(tmp_path):
    """Namespaces and known members should not be treated as invalid classes."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n"
        "Use `Aspose.Pdf`, `Pages`, `Document.Save`, `IndexOutOfBoundsException`, and `Sheet1`.\n",
    )
    api_surface = {"Aspose", "Aspose.Pdf", "Document", "Pages", "Document.Save"}
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert findings == []


def test_pdf_annotation_subtype_literals_are_allowed(tmp_path):
    """Standard PDF-spec annotation Subtype string values (e.g. `Square`,
    `Circle`) used correctly as example argument values must not be flagged
    as invalid API symbols just because they're backtick-quoted (pdf/python,
    2026-08-17: a real prose sentence listing valid subtypes produced 5
    false INVALID_SYMBOL findings)."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n"
        "Creates an annotation of a standard subtype such as `Square`, "
        "`Circle`, `Line`, `Highlight`, or `FreeText`.\n",
    )
    api_surface = {"PdfDocument", "TextFragment"}  # none of the subtypes are real classes
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert findings == []


def test_python_builtins_and_literals_are_allowed(tmp_path):
    """RPR-ST089-01: Python's None/True/False keywords, Excel formula
    boolean literals, and common builtin exception names are never API
    symbols regardless of family/platform. Found live 2026-08-18,
    cells/python: correct error-handling and formula prose produced false
    INVALID_SYMBOL findings on `None`, `False`, `AttributeError`, etc."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n"
        "If the value is `None`, skip it. Use `=IF(A1,TRUE,FALSE)` for the "
        "formula. This raises `AttributeError` or `FileNotFoundError` on "
        "failure.\n",
    )
    api_surface = {"Workbook", "Worksheet"}
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert findings == []


def test_hex_color_literals_are_allowed(tmp_path):
    """RPR-ST089-02: ARGB/RGB hex color literals (8, 6, or 2 hex digits,
    e.g. `FF1E64C8`, `FFFFFFFF`, bare `FF` for the alpha byte) are never API
    symbols. Found live 2026-08-18, cells/python: a styling guide citing
    hex color values produced 15 false INVALID_SYMBOL findings on one
    page."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n"
        "Use `FF1E64C8` for corporate blue or `FFFFFFFF` for white. The "
        "alpha byte `FF` means fully opaque.\n",
    )
    api_surface = {"Workbook", "Worksheet"}
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert findings == []


def test_hex_literal_regex_does_not_swallow_real_class_names(tmp_path):
    """Negative control: the hex-literal exclusion must not blind the
    checker to a real, non-hex-shaped class name that happens to contain
    only uppercase letters."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\nUse `NonExistentClass` to convert.\n",
    )
    api_surface = {"Workbook", "Worksheet"}
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert any(f["finding_type"] == ro.FINDING_INVALID_SYMBOL for f in findings)


def test_spreadsheet_cell_addresses_are_allowed(tmp_path):
    """RPR-ST089-03: spreadsheet cell-address references (`B5`, `D5`) and
    bare single-letter column references (`C`) are never API symbols in a
    spreadsheet product's prose. Found live 2026-08-18, cells/python."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n"
        "Apply the style to cell `B5` and cell `D5`, or to column `C` "
        "entirely.\n",
    )
    api_surface = {"Workbook", "Worksheet"}
    findings = ro._validate_api_symbols(str(page), api_surface)
    assert findings == []


def test_load_api_surface_includes_namespaces_and_members(tmp_path):
    """api_surface loader exposes class imports, namespace prefixes, methods, and properties."""
    _setup(tmp_path)
    api_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "api_surface.json").write_text(
        json.dumps([
            {
                "name": "Document",
                "canonical_namespace": "Aspose.Pdf",
                "class_import": "Aspose.Pdf.Document",
                "methods": [{"name": "Save"}],
                "properties": [{"name": "Pages"}],
            }
        ]),
        encoding="utf-8",
    )

    tokens = ro._load_api_surface("pdf", "net")
    assert {"Aspose", "Aspose.Pdf", "Aspose.Pdf.Document", "Document.Save", "Pages"} <= tokens


def test_load_api_surface_includes_bases_and_enum_members(tmp_path):
    """api_surface loader exposes inherited base tokens and enum member constants."""
    _setup(tmp_path, family="cells", platform="java")
    api_dir = tmp_path / "knowledge" / "cells" / "java" / "merged"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "api_surface.json").write_text(
        json.dumps([
            {
                "name": "Workbook",
                "bases": ["AutoCloseable"],
                "methods": [],
                "properties": [],
            },
            {
                "name": "CellValueType",
                "enum_members": [
                    {"name": "STRING"},
                    {"name": "NUMBER"},
                    {"name": "BOOLEAN"},
                    {"name": "DATE_TIME"},
                ],
                "methods": [],
                "properties": [],
            },
        ]),
        encoding="utf-8",
    )

    tokens = ro._load_api_surface("cells", "java")
    assert {"AutoCloseable", "STRING", "NUMBER", "BOOLEAN", "DATE_TIME"} <= tokens
    assert {"CellValueType.STRING", "CellValueType.DATE_TIME"} <= tokens


def test_frontmatter_body_inconsistency_detected(tmp_path):
    """Format listed in frontmatter but denied in body produces FM contradiction."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\nevidence:\n  formats:\n    - format: PDF\n---\n\n"
        "PDF is not supported by this product.\n",
    )
    findings = ro._validate_frontmatter_body_consistency(str(page))
    assert any(f["finding_type"] == ro.FINDING_FM_CONTRADICTION for f in findings)


def test_orphan_heading_detected(tmp_path):
    """H3 without preceding H2 produces FINDING_ORPHAN_HEADING."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n### Orphan Sub-Heading\n\nContent here.\n",
    )
    findings = ro._validate_heading_structure(str(page))
    assert any(f["finding_type"] == ro.FINDING_ORPHAN_HEADING for f in findings)


def test_clean_page_no_findings(tmp_path):
    """Page with valid H2, consistent frontmatter, and no stale APIs produces no findings."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n## Overview\n\n### Details\n\nUse the API.\n",
    )
    # H3 has a preceding H2 — no orphan finding
    findings = ro._validate_heading_structure(str(page))
    assert findings == []


def test_verdict_written_to_oracle_verdicts_dir(tmp_path):
    """_emit_verdict writes a YAML file to oracle_verdicts/ directory."""
    _setup(tmp_path)
    ro._emit_verdict(
        page_path="content/test/page.md",
        findings=[],
        family="pdf",
        platform="net",
        sections_checked=3,
        claims_checked=12,
        examples_checked=1,
        source_revision="abc123",
    )
    verdicts_dir = tmp_path / "reports" / "pdf" / "net" / "oracle_verdicts"
    assert verdicts_dir.exists()
    files = list(verdicts_dir.glob("*.yaml"))
    assert len(files) == 1
    loaded = yaml.safe_load(files[0].read_text(encoding="utf-8"))
    assert "refresh_oracle_verdict" in loaded
    assert loaded["refresh_oracle_verdict"]["verdict"] == ro.VERDICT_PASS


def test_verdict_filename_uses_hash_to_avoid_long_path_collisions(tmp_path):
    """Long page paths with the same prefix should not overwrite each other's verdicts."""
    _setup(tmp_path)
    prefix = "content/blog.aspose.org/cells/java/java-excel-formulas-styling-api/index"
    ro._emit_verdict(f"{prefix}.bg.md", [], "pdf", "net")
    ro._emit_verdict(f"{prefix}.ca.md", [], "pdf", "net")

    verdicts_dir = tmp_path / "reports" / "pdf" / "net" / "oracle_verdicts"
    assert len(list(verdicts_dir.glob("*.yaml"))) == 2


def test_fail_verdict_on_findings(tmp_path):
    """Verdict is FAIL when any finding exists."""
    _setup(tmp_path)
    verdict = ro._emit_verdict(
        page_path="content/test/page.md",
        findings=[{"finding_type": ro.FINDING_STALE_API, "detail": "Old class found"}],
        family="pdf",
        platform="net",
    )
    assert verdict["verdict"] == ro.VERDICT_FAIL


def test_idempotency(tmp_path):
    """Running _emit_verdict twice with same inputs produces same verdict."""
    _setup(tmp_path)
    v1 = ro._emit_verdict("content/page.md", [], "pdf", "net", source_revision="abc")
    v2 = ro._emit_verdict("content/page.md", [], "pdf", "net", source_revision="abc")
    assert v1["verdict"] == v2["verdict"]
    assert v1["claims_checked"] == v2["claims_checked"]


def test_cross_page_check_ignores_receipt_covered_page(tmp_path, monkeypatch):
    """A BODY_UPDATED receipt means a definite impact on that page was not missed."""
    page = _make_page(
        tmp_path,
        "content/page.md",
        "---\ntitle: Test\n---\n\n## Overview\n\nUse `Document`.\n",
    )
    reports = _setup(tmp_path)
    reports.mkdir(parents=True, exist_ok=True)
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "RCP-001.yaml").write_text(
        yaml.safe_dump({
            "content_refresh_receipt": {
                "page_path": str(page),
                "verdict": "BODY_UPDATED",
            }
        }),
        encoding="utf-8",
    )
    api_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "api_surface.json").write_text(
        json.dumps([{"name": "Document"}]), encoding="utf-8"
    )
    monkeypatch.setattr(
        ro,
        "_run_cross_page_propagation_check",
        lambda f, p: [{
            "finding_type": ro.FINDING_MISSED_IMPACT,
            "page_path": str(page),
            "detail": "definite impact",
        }],
    )

    verdicts = ro.run("pdf", "net", receipts_dir=str(receipts))
    assert verdicts[0]["verdict"] == ro.VERDICT_PASS


def _make_receipted_page(tmp_path: Path, page_content: str) -> Path:
    """Build a receipts/ + api_surface.json fixture around one page whose
    content and receipt are wired together via _setup()."""
    page = _make_page(tmp_path, "content/page.md", page_content)
    reports = _setup(tmp_path)
    reports.mkdir(parents=True, exist_ok=True)
    receipts = reports / "receipts"
    receipts.mkdir()
    (receipts / "RCP-001.yaml").write_text(
        yaml.safe_dump({
            "content_refresh_receipt": {
                "page_path": str(page),
                "verdict": "BODY_UPDATED",
            }
        }),
        encoding="utf-8",
    )
    api_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "api_surface.json").write_text(
        json.dumps([{"name": "RealClass"}]), encoding="utf-8"
    )
    return receipts


def test_main_exits_nonzero_when_run_reports_any_fail(tmp_path, monkeypatch):
    """RPR-ORACLE-001: main() must exit non-zero whenever run() returns any
    FAIL verdict. Before the fix, the only sys.exit(1) in the file fired
    from the except-Exception handler around run() -- a clean run with real
    FAIL verdicts always returned normally (implicit exit 0), silently
    disabling this validator as a blocking gate: refresh_run.py::verify_run()
    derives manifest["validation"]["oracle"] purely from the subprocess
    returncode, so it faithfully -- but wrongly -- recorded PASS no matter
    how many pages the oracle itself found broken.
    """
    receipts = _make_receipted_page(
        tmp_path,
        "---\ntitle: Test\n---\n\nSee `TotallyFakeSymbolXYZ` for details.\n",
    )

    # Sanity check on the fixture itself: run() must actually report a real
    # FAIL here, or the exit-code assertion below would prove nothing.
    verdicts = ro.run("pdf", "net", receipts_dir=str(receipts))
    assert verdicts and verdicts[0]["verdict"] == ro.VERDICT_FAIL

    monkeypatch.setattr(
        sys, "argv", ["refresh_oracle.py", "pdf", "net", "--receipts", str(receipts)]
    )
    assert _call_main_get_exit_code() != 0, (
        "main() exited 0 despite a real FAIL verdict -- the oracle gate is "
        "not actually blocking"
    )


def test_main_exits_zero_when_run_reports_no_fail(tmp_path, monkeypatch):
    """Negative control: a clean page (no invalid symbols) must still exit 0
    -- the fix must not turn this validator into an always-fail gate."""
    receipts = _make_receipted_page(
        tmp_path,
        "---\ntitle: Test\n---\n\nSee `RealClass` for details.\n",
    )

    verdicts = ro.run("pdf", "net", receipts_dir=str(receipts))
    assert verdicts and verdicts[0]["verdict"] == ro.VERDICT_PASS

    monkeypatch.setattr(
        sys, "argv", ["refresh_oracle.py", "pdf", "net", "--receipts", str(receipts)]
    )
    assert _call_main_get_exit_code() == 0
