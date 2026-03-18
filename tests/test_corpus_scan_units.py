"""Unit tests for pure functions in scripts/corpus_scan.py."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from corpus_scan import (  # noqa: E402
    _parse_frontmatter,
    _extract_structure,
    _scan_pages,
    _load_golden_data,
    _determine_richness_tier,
)

FIXTURE_CONTENT = REPO_ROOT / "tests" / "fixtures" / "content"
SAMPLE_PAGE = FIXTURE_CONTENT / "docs.aspose.org" / "en" / "words" / "python" / "sample.md"


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------

def test_parse_frontmatter_extracts_title():
    text = "---\ntitle: My Title\ntype: docs\n---\n\n# Content"
    fm = _parse_frontmatter(text)
    assert fm.get("title") == "My Title"


def test_parse_frontmatter_extracts_type():
    text = "---\ntitle: My Title\ntype: docs\n---\n\n# Content"
    fm = _parse_frontmatter(text)
    assert fm.get("type") == "docs"


def test_parse_frontmatter_no_frontmatter():
    text = "# Just a heading\n\nSome content without frontmatter."
    fm = _parse_frontmatter(text)
    assert fm == {}


def test_parse_frontmatter_returns_dict():
    text = "---\nkey: value\n---\n"
    fm = _parse_frontmatter(text)
    assert isinstance(fm, dict)


def test_parse_frontmatter_sample_file():
    text = SAMPLE_PAGE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert "title" in fm
    assert "type" in fm


# ---------------------------------------------------------------------------
# _extract_structure
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
---
title: Test
---

## Overview

Some introductory text about the topic with enough words to be useful.

## Installation

```bash
pip install something
```

## Usage

```python
from module import Class
obj = Class()
obj.method()
```

### Advanced Usage

More details about advanced features and configuration options.
"""


def test_extract_structure_word_count():
    result = _extract_structure(SAMPLE_MD)
    assert result["word_count"] > 0


def test_extract_structure_h2_headings():
    result = _extract_structure(SAMPLE_MD)
    h2 = result["h2_headings"]
    assert "Overview" in h2
    assert "Installation" in h2
    assert "Usage" in h2


def test_extract_structure_h3_headings():
    result = _extract_structure(SAMPLE_MD)
    h3 = result["h3_headings"]
    assert "Advanced Usage" in h3


def test_extract_structure_code_blocks():
    result = _extract_structure(SAMPLE_MD)
    blocks = result["code_blocks"]
    assert len(blocks) >= 2
    langs = [b["language"] for b in blocks]
    assert "bash" in langs
    assert "python" in langs


def test_extract_structure_returns_required_keys():
    result = _extract_structure(SAMPLE_MD)
    for key in ("h2_headings", "h3_headings", "code_blocks", "shortcodes", "word_count"):
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# _scan_pages
# ---------------------------------------------------------------------------

def test_scan_pages_finds_fixture_content():
    content_dir = FIXTURE_CONTENT / "docs.aspose.org" / "en" / "words" / "python"
    pages = _scan_pages(content_dir, min_words=10)
    assert len(pages) >= 1


def test_scan_pages_returns_list():
    content_dir = FIXTURE_CONTENT / "docs.aspose.org" / "en" / "words" / "python"
    pages = _scan_pages(content_dir, min_words=1)
    assert isinstance(pages, list)


def test_scan_pages_page_has_required_fields():
    content_dir = FIXTURE_CONTENT / "docs.aspose.org" / "en" / "words" / "python"
    pages = _scan_pages(content_dir, min_words=1)
    assert pages
    page = pages[0]
    for key in ("path", "frontmatter", "structure"):
        assert key in page, f"Missing key: {key}"


def test_scan_pages_min_words_filter():
    content_dir = FIXTURE_CONTENT / "docs.aspose.org" / "en" / "words" / "python"
    pages_low = _scan_pages(content_dir, min_words=1)
    pages_high = _scan_pages(content_dir, min_words=999999)
    assert len(pages_low) >= len(pages_high)


def test_scan_pages_empty_dir(tmp_path):
    pages = _scan_pages(tmp_path, min_words=1)
    assert pages == []


# ---------------------------------------------------------------------------
# _load_golden_data
# ---------------------------------------------------------------------------

def _make_golden_index(pages):
    """Create a minimal golden _index.json structure."""
    return {
        "schema_version": 1,
        "generated_at": "2026-03-18T00:00:00Z",
        "page_count": len(pages),
        "pages": pages,
        "role_variant_map": {},
        "tier_selection": {"C": "minimal", "B": "standard", "A": "standard"},
    }


def test_load_golden_data_with_valid_index(tmp_path, monkeypatch):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    index = _make_golden_index([{
        "page_role": "workflow_page",
        "variant": "standard",
        "grade": "A",
        "source_path": "docs.aspose.org/feature.md",
        "total_word_count": 200,
        "sections": [{"heading": "Installation", "structural_contract": "code (2)"}],
        "style_rubric": {"prose_before_code": True},
    }])
    (golden_dir / "_index.json").write_text(json.dumps(index))
    monkeypatch.setattr("corpus_scan.resolve_golden_dir", lambda: golden_dir)

    result = _load_golden_data("docs")
    assert len(result["golden_anchors"]) == 1
    assert result["golden_anchors"][0]["page_role"] == "workflow_page"
    assert result["golden_style_rubric"]["prose_before_code"] is True
    assert "standard" in result["available_variants"]
    assert "tier_selection" in result


def test_load_golden_data_missing_index(tmp_path, monkeypatch):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    # No _index.json created
    monkeypatch.setattr("corpus_scan.resolve_golden_dir", lambda: golden_dir)

    result = _load_golden_data("docs")
    assert result == {}


def test_load_golden_data_unknown_site_type(tmp_path, monkeypatch):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    index = _make_golden_index([{
        "page_role": "workflow_page",
        "variant": "standard",
        "grade": "A",
        "source_path": "docs.aspose.org/feature.md",
        "total_word_count": 200,
        "sections": [],
        "style_rubric": {},
    }])
    (golden_dir / "_index.json").write_text(json.dumps(index))
    monkeypatch.setattr("corpus_scan.resolve_golden_dir", lambda: golden_dir)

    result = _load_golden_data("nonexistent_type")
    assert result == {}


def test_load_golden_data_collects_structural_contracts(tmp_path, monkeypatch):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    index = _make_golden_index([{
        "page_role": "workflow_page",
        "variant": "standard",
        "grade": "A",
        "source_path": "docs.aspose.org/feature.md",
        "total_word_count": 200,
        "sections": [
            {"heading": "Installation", "structural_contract": "code (2) | list (1)"},
            {"heading": "Usage", "structural_contract": "code (3)"},
        ],
        "style_rubric": {},
    }])
    (golden_dir / "_index.json").write_text(json.dumps(index))
    monkeypatch.setattr("corpus_scan.resolve_golden_dir", lambda: golden_dir)

    result = _load_golden_data("docs")
    contracts = result["golden_structural_contracts"]
    assert "workflow_page/standard/Installation" in contracts
    assert "workflow_page/standard/Usage" in contracts
    assert contracts["workflow_page/standard/Installation"] == "code (2) | list (1)"


# ---------------------------------------------------------------------------
# _determine_richness_tier
# ---------------------------------------------------------------------------

def test_richness_tier_c_low_pages():
    assert _determine_richness_tier(2, "test", "python") == "C"


def test_richness_tier_b_medium_pages():
    assert _determine_richness_tier(5, "test", "python") == "B"


def test_richness_tier_b_high_pages_no_api():
    # 10 pages but no API classes (knowledge dir doesn't exist) → B not A
    assert _determine_richness_tier(10, "test", "python") == "B"
