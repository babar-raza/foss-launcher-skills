"""
Tests for scripts/pipeline/commands/content/claim_parser.py.

Min required: 8 tests. This file has 9.
"""

import json
import pytest
from pathlib import Path

import commands.content.claim_parser as cp


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    yield
    cp.configure(content_root="content")


def _make_page(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────

def test_api_name_detection_in_code_blocks():
    """Backtick-wrapped CamelCase.Method patterns are detected as API_REFERENCE."""
    text = "Use `Document.Save` to write the output file."
    symbols = cp._extract_api_symbols(text)
    assert "Document.Save" in symbols


def test_api_name_detection_in_prose():
    """CamelCase class names in prose are detected when no backtick symbols exist."""
    text = "The TextFragment class represents a piece of text."
    symbols = cp._extract_api_symbols(text)
    assert any("TextFragment" in s for s in symbols)


def test_section_segmentation_correctness(tmp_path):
    """Body with H2 headings is split into correct sections."""
    content = """---
title: Test
---

## Installation

Install the package.

## Usage

Use the API.
"""
    p = _make_page(tmp_path, "test.md", content)
    claim_map = cp.parse_page(str(p))
    section_ids = [s["section_id"] for s in claim_map["sections"]]
    assert "installation" in section_ids
    assert "usage" in section_ids
    assert len(claim_map["sections"]) == 2


def test_format_name_detection():
    """PDF, DOCX, SVG etc. are detected as FORMAT_CLAIM."""
    text = "Convert documents from PDF to DOCX or SVG."
    formats = cp._extract_format_claims(text)
    assert "PDF" in formats
    assert "DOCX" in formats
    assert "SVG" in formats


def test_discovery_includes_products_surface(tmp_path):
    page = (
        tmp_path
        / "products.aspose.org/en/pdf/net/index.md"
    )
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: PDF\n---\n", encoding="utf-8")
    cp.configure(content_root=str(tmp_path))
    assert page in {Path(item) for item in cp._discover_pages("pdf", "net")}


def test_feature_claim_extraction():
    """Feature keywords (supports, converts, exports) are captured."""
    text = "Aspose.PDF supports PDF export and converts files."
    features = cp._extract_feature_claims(text)
    assert any("support" in f for f in features)
    assert any("convert" in f or "export" in f for f in features)


def test_version_claim_extraction():
    """Version strings like .NET 6, v26.5.0 are detected."""
    text = "Requires .NET 6 or higher. Compatible with v26.5.0 release."
    versions = cp._extract_version_claims(text)
    assert any(".NET" in v for v in versions)
    assert any("26.5.0" in v for v in versions)


def test_idempotency_same_input_same_output(tmp_path):
    """Parsing the same file twice produces identical output."""
    content = """---
title: Test
---

## Overview

Use `PdfDocument` to load a PDF file and convert to PDF format.
"""
    p = _make_page(tmp_path, "idempotent.md", content)
    result1 = cp.parse_page(str(p))
    result2 = cp.parse_page(str(p))
    assert result1 == result2


def test_empty_section_handling(tmp_path):
    """Section with no claim-bearing lines produces empty claims list."""
    content = """---
title: Test
---

## Empty Section

this section has no api names, no formats, no verbs, no versions here at all.
just a few lowercase words that match nothing in the extractors.
"""
    p = _make_page(tmp_path, "empty_section.md", content)
    result = cp.parse_page(str(p))
    assert len(result["sections"]) == 1
    # The plain text lines have no detectable claims
    assert result["sections"][0]["claims"] == []


def test_claim_map_written_to_output_dir(tmp_path):
    """run_file() writes a valid JSON claim_map to the output directory."""
    content = """---
title: Test
---

## Install

Install `Aspose.PDF` using NuGet for .NET 6.
"""
    p = _make_page(tmp_path, "install.md", content)
    out_dir = str(tmp_path / "claim_maps")
    cp.run_file(str(p), out_dir)
    files = list(Path(out_dir).glob("*.claim_map.json"))
    assert len(files) == 1
    loaded = json.loads(files[0].read_text(encoding="utf-8"))
    assert "page_path" in loaded
    assert "sections" in loaded
    total = sum(len(s["claims"]) for s in loaded["sections"])
    assert total >= 1
