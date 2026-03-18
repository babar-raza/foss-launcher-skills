"""Tests for scripts/golden_conformance.py — golden conformance scorer."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from golden_conformance import (
    _dim_block_type_coverage,
    _dim_code_density_alignment,
    _dim_depth_proportionality,
    _dim_section_coverage,
    _dim_section_order,
    _get_block_types,
    _match_sections,
    _normalize_heading,
    _prose_word_count,
    _split_sections,
    score_conformance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_golden_section(heading, word_count=50, code=True, has_list=False, has_table=False):
    """Create a mock golden section dict."""
    seq = ["paragraph"]
    if code:
        seq.append("code")
    if has_list:
        seq.append("list")
    if has_table:
        seq.append("table")
    return {
        "heading": heading,
        "word_count": word_count,
        "code_block_count": 1 if code else 0,
        "list_block_count": 3 if has_list else 0,
        "table_count": 1 if has_table else 0,
        "block_sequence": seq,
        "code_to_prose_ratio": 0.4 if code else 0.0,
        "has_code": code,
        "has_list": has_list,
        "has_table": has_table,
    }


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

class TestSplitSections:
    def test_basic_split(self):
        body = "## Intro\n\nSome text\n\n## Body\n\nMore text\n"
        sections = _split_sections(body)
        assert len(sections) == 2
        assert sections[0][0] == "Intro"
        assert sections[1][0] == "Body"

    def test_preserves_body(self):
        body = "## Heading\n\nParagraph text here\n\n```python\ncode()\n```\n"
        sections = _split_sections(body)
        assert "code()" in sections[0][1]


class TestProseWordCount:
    def test_excludes_code(self):
        text = "Some prose here.\n\n```python\nnot counted\n```\n\nMore prose words."
        assert _prose_word_count(text) > 0
        # Should not count "not counted"
        assert "not" not in text.split("```")[1] or _prose_word_count(text) < len(text.split())


class TestGetBlockTypes:
    def test_detects_code(self):
        text = "Some text\n\n```python\ncode()\n```\n"
        types = _get_block_types(text)
        assert "code" in types
        assert "paragraph" in types

    def test_detects_list(self):
        text = "Intro text\n\n- Item 1\n- Item 2\n"
        types = _get_block_types(text)
        assert "list" in types

    def test_detects_table(self):
        text = "Intro text\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        types = _get_block_types(text)
        assert "table" in types


# ---------------------------------------------------------------------------
# Heading normalization
# ---------------------------------------------------------------------------

class TestNormalizeHeading:
    def test_lowercases(self):
        assert _normalize_heading("Installation Guide") == "installation guide"

    def test_removes_stop_words(self):
        norm = _normalize_heading("Tips and Best Practices")
        assert "and" not in norm.split()

    def test_removes_punctuation(self):
        norm = _normalize_heading("FAQ: Common Questions?")
        assert ":" not in norm
        assert "?" not in norm


# ---------------------------------------------------------------------------
# Section matching
# ---------------------------------------------------------------------------

class TestMatchSections:
    def test_exact_match(self):
        golden = [_make_golden_section("Installation")]
        gen = [("Installation", "Install content")]
        matched = _match_sections(golden, gen)
        assert len(matched) == 1

    def test_substring_match(self):
        golden = [_make_golden_section("Usage Examples")]
        gen = [("Usage Examples and Demos", "Content")]
        matched = _match_sections(golden, gen)
        assert len(matched) == 1

    def test_no_match(self):
        golden = [_make_golden_section("Installation")]
        gen = [("Completely Different", "Content")]
        matched = _match_sections(golden, gen)
        assert len(matched) == 0


# ---------------------------------------------------------------------------
# Dimension scoring
# ---------------------------------------------------------------------------

class TestDimensions:
    def test_section_coverage_full(self):
        golden = [_make_golden_section("A"), _make_golden_section("B")]
        matched = [(0, 0, golden[0], "A", ""), (1, 1, golden[1], "B", "")]
        assert _dim_section_coverage(golden, matched) == 1.0

    def test_section_coverage_partial(self):
        golden = [_make_golden_section("A"), _make_golden_section("B")]
        matched = [(0, 0, golden[0], "A", "")]
        assert _dim_section_coverage(golden, matched) == 0.5

    def test_section_order_preserved(self):
        golden = [_make_golden_section("A"), _make_golden_section("B")]
        matched = [(0, 0, golden[0], "A", ""), (1, 1, golden[1], "B", "")]
        assert _dim_section_order(matched) == 1.0

    def test_section_order_reversed(self):
        golden = [_make_golden_section("A"), _make_golden_section("B")]
        matched = [(0, 1, golden[0], "A", ""), (1, 0, golden[1], "B", "")]
        assert _dim_section_order(matched) == 0.0

    def test_block_type_coverage_identical(self):
        gs = _make_golden_section("A", code=True, has_list=True)
        matched = [(0, 0, gs, "A", "Prose\n\n```python\ncode()\n```\n\n- item\n")]
        score = _dim_block_type_coverage(matched)
        assert score > 0.5

    def test_code_density_alignment_same_ratio(self):
        gs = _make_golden_section("A", code=True)
        gs["code_to_prose_ratio"] = 0.5
        text = "Words " * 50 + "\n```python\n" + "code\n" * 50 + "```\n"
        matched = [(0, 0, gs, "A", text)]
        score = _dim_code_density_alignment(matched)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Integration: score_conformance
# ---------------------------------------------------------------------------

class TestScoreConformance:
    @pytest.fixture
    def setup_golden(self, tmp_path, monkeypatch):
        """Create golden dir with index and a content file."""
        golden_dir = tmp_path / "golden"
        golden_dir.mkdir()

        index = {
            "schema_version": 1,
            "generated_at": "2026-03-18T00:00:00Z",
            "page_count": 1,
            "pages": [{
                "page_role": "workflow_page",
                "variant": "standard",
                "subdomain": "docs.aspose.org",
                "grade": "A",
                "source_path": "docs.aspose.org/feature.md",
                "total_word_count": 100,
                "sections": [
                    _make_golden_section("Installation", 40),
                    _make_golden_section("Usage Examples", 60, has_list=True),
                ],
                "style_rubric": {"prose_before_code": True, "min_code_variety": 2},
            }],
            "role_variant_map": {"workflow_page": ["standard"]},
            "tier_selection": {"C": "minimal", "B": "standard", "A": "standard"},
        }
        (golden_dir / "_index.json").write_text(json.dumps(index))

        # Monkeypatch resolve_golden_dir
        monkeypatch.setattr("golden_conformance.resolve_golden_dir", lambda: golden_dir)

        # Create content file
        content = (
            "---\ntitle: Test\n---\n\n"
            "## Installation\n\n"
            "Install the package via pip for your platform.\n\n"
            "```python\nimport lib\n```\n\n"
            "## Usage Examples\n\n"
            "Here are usage examples for common tasks.\n\n"
            "```python\nlib.convert()\n```\n\n"
            "- Use case one\n"
            "- Use case two\n"
        )
        content_file = tmp_path / "test-page.md"
        content_file.write_text(content)

        return content_file

    def test_good_conformance(self, setup_golden):
        result = score_conformance(setup_golden, "workflow_page", "standard")
        assert "error" not in result
        assert result["conformance_score"] > 0.3
        assert result["matched_sections"] == 2

    def test_missing_golden_page(self, setup_golden):
        result = score_conformance(setup_golden, "nonexistent_role", "standard")
        assert "error" in result

    def test_empty_content(self, tmp_path, monkeypatch):
        golden_dir = tmp_path / "golden"
        golden_dir.mkdir()
        index = {
            "pages": [{
                "page_role": "test",
                "variant": "standard",
                "sections": [_make_golden_section("A")],
            }],
        }
        (golden_dir / "_index.json").write_text(json.dumps(index))
        monkeypatch.setattr("golden_conformance.resolve_golden_dir", lambda: golden_dir)

        content_file = tmp_path / "empty.md"
        content_file.write_text("---\ntitle: Empty\n---\n")
        result = score_conformance(content_file, "test", "standard")
        assert result["conformance_score"] == 0.0
