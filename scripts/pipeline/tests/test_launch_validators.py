"""test_launch_validators.py - Tests for api_symbol_validator and marketing_truth_validator."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from scripts.pipeline.commands.launch.api_symbol_validator import (
    extract_go_blocks,
    validate_file,
)


def _make_md(code_block: str, tmp_path: Path) -> Path:
    p = tmp_path / "test.md"
    FENCE = chr(96) * 3
    lines_out = ["---", "title: Test", "---", "", "## Section", "", FENCE + "go", code_block, FENCE, ""]
    p.write_text(chr(10).join(lines_out), encoding="utf-8")
    return p


def test_extract_go_blocks_basic(tmp_path):
    md = tmp_path / "page.md"
    FENCE = chr(96) * 3
    lines_out = ["# Title", "", FENCE + "go", 'doc := pdf.Open("f.pdf")', FENCE, ""]
    md.write_text(chr(10).join(lines_out), encoding="utf-8")
    blocks = extract_go_blocks(md)
    assert len(blocks) == 1
    assert "pdf.Open" in blocks[0]


def test_extract_go_blocks_no_blocks(tmp_path):
    md = tmp_path / "page.md"
    md.write_text(chr(10).join(["# Title", "", "No code here.", ""]), encoding="utf-8")
    assert extract_go_blocks(md) == []


def test_validate_file_pass_known_symbol(tmp_path):
    """Known symbol pdf.Open should not be flagged."""
    md = _make_md('doc, err := pdf.Open("f.pdf")', tmp_path)
    known_types = {"Document", "Open"}
    known_funcs = {"Open", "OpenWithPassword", "NewDocument"}
    findings = validate_file(md, known_types, known_funcs)
    assert findings == []


def test_validate_file_fail_unknown_symbol(tmp_path):
    """Unknown symbol pdf.NonExistentFunc should be flagged as BLOCKER."""
    md = _make_md('pdf.NonExistentFunc("x")', tmp_path)
    known_types = {"Document"}
    known_funcs = {"Open"}
    findings = validate_file(md, known_types, known_funcs)
    assert len(findings) == 1
    assert findings[0]["severity"] == "BLOCKER"
    assert findings[0]["symbol"] == "pdf.NonExistentFunc"


def test_validate_file_skip_stdlib(tmp_path):
    """fmt.Println should not be flagged as unknown."""
    md = _make_md('fmt.Println("hello")', tmp_path)
    findings = validate_file(md, set(), set())
    assert findings == [], "fmt stdlib should be skipped"


def test_marketing_validator_pass_clean_page(tmp_path):
    """Products page with no forbidden claims should pass."""
    import scripts.pipeline.commands.launch.marketing_truth_validator as mtv
    orig = mtv._REPO_ROOT
    prod_dir = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "go"
    prod_dir.mkdir(parents=True)
    lines_out = ["---", "evidence:", "  apis:", "  - Document.Save", "---", "", "Open and save PDFs.", ""]
    (prod_dir / "_index.md").write_text(chr(10).join(lines_out), encoding="utf-8")
    mtv._REPO_ROOT = tmp_path
    try:
        findings = mtv.check_products_page("pdf", "go")
        blockers = [f for f in findings if f["severity"] == "BLOCKER"]
        assert blockers == [], f"Unexpected blockers: {blockers}"
    finally:
        mtv._REPO_ROOT = orig


def test_marketing_validator_fail_xmp_claim(tmp_path):
    """Products page claiming XMP should be flagged BLOCKER."""
    import scripts.pipeline.commands.launch.marketing_truth_validator as mtv
    prod_dir = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "go"
    prod_dir.mkdir(parents=True)
    lines_out = ["---", "evidence:", "  apis:", "  - Document", "---", "", "Read and write XMP metadata.", ""]
    (prod_dir / "_index.md").write_text(chr(10).join(lines_out), encoding="utf-8")
    orig = mtv._REPO_ROOT
    mtv._REPO_ROOT = tmp_path
    try:
        findings = mtv.check_products_page("pdf", "go")
        blockers = [f for f in findings if f["severity"] == "BLOCKER"]
        assert len(blockers) == 1
        assert "XMP" in blockers[0]["claim"]
    finally:
        mtv._REPO_ROOT = orig

