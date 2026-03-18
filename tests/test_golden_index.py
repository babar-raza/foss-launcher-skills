"""Tests for scripts/golden_index.py — golden corpus indexer."""
import json
import sys
from pathlib import Path

import pytest

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from golden_index import (
    _infer_role_variant,
    _parse_golden_file,
    _parse_sections,
    build_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def golden_dir(tmp_path):
    """Create a minimal golden corpus for testing."""
    # docs workflow page (standard variant)
    docs_dir = tmp_path / "docs.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "developer-guide"
    docs_dir.mkdir(parents=True)
    (docs_dir / "feature.variant-standard.md").write_text(
        '<!-- GOLDEN REFERENCE | Structural Exemplar | Original-Grade: A -->\n'
        '---\n'
        'title: "{{PRODUCT_NAME}} Feature Guide"\n'
        'type: docs\n'
        '---\n'
        '\n'
        '## Installation and Setup\n'
        '\n'
        'To get started with the library, install it via pip.\n'
        '\n'
        '```python\n'
        'import library\n'
        'doc = library.Document()\n'
        '```\n'
        '\n'
        '- Step 1: Install\n'
        '- Step 2: Import\n'
        '- Step 3: Use\n'
        '\n'
        '## Usage Examples\n'
        '\n'
        'Here are some examples of common operations.\n'
        '\n'
        '```python\n'
        'result = doc.convert("output.pdf")\n'
        'print(result)\n'
        '```\n'
        '\n'
        '## Tips and Best Practices\n'
        '\n'
        'Always close resources after use. Use context managers when possible.\n'
        'Check the API reference for advanced options and configuration.\n'
    )

    # docs workflow page (minimal variant)
    (docs_dir / "feature.variant-minimal.md").write_text(
        '<!-- GOLDEN REFERENCE | Structural Exemplar | Original-Grade: B -->\n'
        '---\n'
        'title: "{{PRODUCT_NAME}} Quick Guide"\n'
        'type: docs\n'
        '---\n'
        '\n'
        '## Quick Start\n'
        '\n'
        'Install and run a basic conversion task.\n'
        '\n'
        '```python\n'
        'import library\n'
        'library.convert("input.docx", "output.pdf")\n'
        '```\n'
    )

    # KB howto (standard variant)
    kb_dir = tmp_path / "kb.aspose.org" / "__FAMILY__" / "__PLATFORM__"
    kb_dir.mkdir(parents=True)
    (kb_dir / "howto.variant-standard.md").write_text(
        '<!-- GOLDEN REFERENCE | Structural Exemplar | Original-Grade: B+ -->\n'
        '---\n'
        'title: "How to Convert Documents"\n'
        'type: topic\n'
        '---\n'
        '\n'
        '## Step-by-Step Guide\n'
        '\n'
        'Follow these steps to convert a document from one format to another.\n'
        '\n'
        '```python\n'
        'from library import Converter\n'
        'converter = Converter()\n'
        'converter.convert("input.docx", "output.pdf")\n'
        '```\n'
        '\n'
        '## Common Issues\n'
        '\n'
        'If you encounter errors, check the following common issues:\n'
        '\n'
        '| Issue | Cause | Fix |\n'
        '|-------|-------|-----|\n'
        '| FileNotFound | Wrong path | Check file exists |\n'
        '| FormatError | Unsupported | Check formats.json |\n'
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Role/variant inference tests
# ---------------------------------------------------------------------------

class TestInferRoleVariant:
    def test_docs_developer_guide_standard(self, golden_dir):
        path = golden_dir / "docs.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "developer-guide" / "feature.variant-standard.md"
        role, variant = _infer_role_variant(path, golden_dir)
        assert role == "workflow_page"
        assert variant == "standard"

    def test_docs_developer_guide_minimal(self, golden_dir):
        path = golden_dir / "docs.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "developer-guide" / "feature.variant-minimal.md"
        role, variant = _infer_role_variant(path, golden_dir)
        assert role == "workflow_page"
        assert variant == "minimal"

    def test_kb_howto_standard(self, golden_dir):
        path = golden_dir / "kb.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "howto.variant-standard.md"
        role, variant = _infer_role_variant(path, golden_dir)
        assert role == "howto_article"
        assert variant == "standard"

    def test_kb_faq(self, tmp_path):
        path = tmp_path / "kb.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "faq.md"
        role, variant = _infer_role_variant(path, tmp_path)
        assert role == "faq"
        assert variant == "standard"

    def test_blog(self, tmp_path):
        path = tmp_path / "blog.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "introducing-PRODUCT" / "index.md"
        role, variant = _infer_role_variant(path, tmp_path)
        assert role == "feature_blog"
        assert variant == "standard"

    def test_reference_standard(self, tmp_path):
        path = tmp_path / "reference.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "reference.variant-standard.md"
        role, variant = _infer_role_variant(path, tmp_path)
        assert role == "api_reference"
        assert variant == "standard"


# ---------------------------------------------------------------------------
# Section parsing tests
# ---------------------------------------------------------------------------

class TestParseSections:
    def test_parses_headings(self):
        body = "## First\n\nSome content here with enough words to pass the filter.\n\n## Second\n\nMore content with enough prose words to count.\n"
        sections = _parse_sections(body)
        assert len(sections) == 2
        assert sections[0]["heading"] == "First"
        assert sections[1]["heading"] == "Second"

    def test_counts_code_blocks(self):
        body = "## Example\n\nHere is a code example for the conversion task.\n\n```python\nimport lib\nlib.run()\n```\n\nAnother example follows below.\n\n```python\nlib.stop()\n```\n"
        sections = _parse_sections(body)
        assert sections[0]["code_block_count"] == 2
        assert sections[0]["has_code"] is True

    def test_detects_lists(self):
        body = "## Steps\n\nFollow these steps carefully and completely.\n\n- Step one\n- Step two\n- Step three\n"
        sections = _parse_sections(body)
        assert sections[0]["has_list"] is True
        assert sections[0]["list_block_count"] == 3

    def test_detects_tables(self):
        body = "## Formats\n\nSupported formats for this product are listed below.\n\n| Format | Support |\n|--------|--------|\n| PDF | Yes |\n"
        sections = _parse_sections(body)
        assert sections[0]["has_table"] is True

    def test_structural_contract_generated(self):
        body = "## Example\n\nSome prose content for the example section.\n\n```python\ncode()\n```\n"
        sections = _parse_sections(body)
        assert "structural_contract" in sections[0]
        assert "Block sequence" in sections[0]["structural_contract"]

    def test_skips_near_empty_sections(self):
        body = "## Empty\n\nHi\n\n## Full\n\nThis section has enough words to pass the minimum threshold.\n"
        sections = _parse_sections(body)
        assert len(sections) == 1
        assert sections[0]["heading"] == "Full"


# ---------------------------------------------------------------------------
# File parsing tests
# ---------------------------------------------------------------------------

class TestParseGoldenFile:
    def test_parses_standard_file(self, golden_dir):
        path = golden_dir / "docs.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "developer-guide" / "feature.variant-standard.md"
        page = _parse_golden_file(path, golden_dir)
        assert page is not None
        assert page["page_role"] == "workflow_page"
        assert page["variant"] == "standard"
        assert page["grade"] == "A"
        assert len(page["sections"]) >= 2

    def test_extracts_style_rubric(self, golden_dir):
        path = golden_dir / "docs.aspose.org" / "__FAMILY__" / "__PLATFORM__" / "developer-guide" / "feature.variant-standard.md"
        page = _parse_golden_file(path, golden_dir)
        rubric = page["style_rubric"]
        assert "prose_before_code" in rubric
        assert "min_code_variety" in rubric
        assert isinstance(rubric["prose_before_code"], bool)

    def test_returns_none_for_empty_file(self, tmp_path):
        empty = tmp_path / "docs.aspose.org" / "empty.md"
        empty.parent.mkdir(parents=True)
        empty.write_text("")
        result = _parse_golden_file(empty, tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Full index build tests
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_indexes_all_files(self, golden_dir):
        index = build_index(golden_dir)
        assert index["page_count"] == 3
        assert index["schema_version"] == 1
        assert "generated_at" in index

    def test_role_variant_map(self, golden_dir):
        index = build_index(golden_dir)
        rvm = index["role_variant_map"]
        assert "workflow_page" in rvm
        assert "minimal" in rvm["workflow_page"]
        assert "standard" in rvm["workflow_page"]
        assert "howto_article" in rvm

    def test_tier_selection(self, golden_dir):
        index = build_index(golden_dir)
        ts = index["tier_selection"]
        assert ts["C"] == "minimal"
        assert ts["A"] == "standard"
        assert ts["B"] == "standard"

    def test_pages_have_required_fields(self, golden_dir):
        index = build_index(golden_dir)
        for page in index["pages"]:
            assert "page_role" in page
            assert "variant" in page
            assert "grade" in page
            assert "source_path" in page
            assert "sections" in page
            assert "style_rubric" in page
            assert "total_word_count" in page

    def test_sections_have_structural_contracts(self, golden_dir):
        index = build_index(golden_dir)
        for page in index["pages"]:
            for section in page["sections"]:
                assert "structural_contract" in section
                assert "excerpt" in section
                assert "block_sequence" in section

    def test_skips_readme(self, golden_dir):
        (golden_dir / "README.md").write_text("# Golden Corpus\nDocumentation file.")
        index = build_index(golden_dir)
        paths = [p["source_path"] for p in index["pages"]]
        assert not any("README.md" in p for p in paths)
