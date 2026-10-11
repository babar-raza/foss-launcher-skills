"""
Tests for scripts/pipeline/commands/ops/prose_stale_scan.py

G-15 Removed-API Prose-Scan Hardening.

Covers:
- test_detects_stale_prose_api_ref      — body mention of removed API is detected
- test_ignores_frontmatter              — removed API in YAML frontmatter is NOT detected
- test_ignores_evidence_apis            — removed API in evidence: YAML block is NOT detected
- test_ignores_see_also_section         — removed API in ## See Also section is NOT detected
- test_ignores_pure_link_lines          — removed API in [text](url) line is NOT detected
- test_no_false_partial_match           — "Workbook" does NOT match "WorkbookDesigner"
- test_machine_readable_output          — scan_file returns valid JSON-serializable dicts
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path

import pytest

# Bootstrap path so imports work when running from repo root
_TEST_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _TEST_DIR.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.prose_stale_scan import (
    build_patterns,
    scan_file,
    _is_pure_link_line,
    _strip_frontmatter,
    CONFIDENCE_HIGH,
    CONFIDENCE_MED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp_md(tmp_path: Path, content: str) -> Path:
    """Write a temporary markdown file and return its path."""
    p = tmp_path / "page.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _patterns(names: list[str]) -> dict[str, re.Pattern]:
    return build_patterns(names)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDetectsStaleProseApiRef:
    """Removed API name in the body text is detected."""

    def test_simple_prose_mention(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test Page
            ---

            Use the `WorksheetModel` class to inspect sheet metadata.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 1, f"Expected 1 hit, got {hits}"
        hit = hits[0]
        assert hit["api_name"] == "WorksheetModel"
        assert hit["finding"] == "PROSE_STALE_API_REF"
        assert hit["line_number"] > 0

    def test_multiple_apis_in_body(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test Page
            ---

            The WorkbookModel stores workbook-level properties.
            You can also use DiagnosticBag to collect parse errors.
        """)
        patterns = _patterns(["WorkbookModel", "DiagnosticBag"])
        hits = scan_file(md, patterns)
        api_names = {h["api_name"] for h in hits}
        assert "WorkbookModel" in api_names
        assert "DiagnosticBag" in api_names

    def test_api_in_table_row(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            | Class | Purpose |
            |-------|---------|
            | WorksheetModel | Represents a worksheet |
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) >= 1
        # Table lines get lower confidence
        assert hits[0]["confidence"] < CONFIDENCE_HIGH


class TestIgnoresFrontmatter:
    """Removed API name inside the YAML frontmatter is NOT flagged."""

    def test_api_only_in_frontmatter(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: WorksheetModel Guide
            description: Covers the WorksheetModel class.
            apis:
              - WorksheetModel
            ---

            This page describes how to load a workbook.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 0, f"Expected 0 hits (frontmatter only), got {hits}"

    def test_api_in_frontmatter_and_body(self, tmp_path: Path):
        """API in both places: only the body occurrence should be counted."""
        md = _write_tmp_md(tmp_path, """\
            ---
            title: WorksheetModel Guide
            apis:
              - WorksheetModel
            ---

            The WorksheetModel class has been removed in this release.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 1, f"Expected 1 hit (body only), got {hits}"


class TestIgnoresEvidenceApis:
    """Removed API name inside evidence: YAML block in body is NOT flagged."""

    def test_api_in_evidence_block(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            evidence:
              apis:
                - WorksheetModel
            ---

            This page does not mention the removed class in prose.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 0, (
            f"Frontmatter evidence should not produce hits, got {hits}"
        )


class TestIgnoresSeeAlsoSection:
    """Removed API name in ## See Also section is NOT flagged."""

    def test_api_only_in_see_also(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            This page covers workbook operations.

            ## See Also

            - WorksheetModel reference
            - [WorkbookModel docs](/docs/workbook-model)
        """)
        patterns = _patterns(["WorksheetModel", "WorkbookModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 0, f"See Also content should not be flagged, got {hits}"

    def test_api_in_body_before_see_also(self, tmp_path: Path):
        """Body before See Also is still checked; after is skipped."""
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            Use WorksheetModel to inspect sheets.

            ## See Also

            - WorkbookModel reference
        """)
        patterns = _patterns(["WorksheetModel", "WorkbookModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 1
        assert hits[0]["api_name"] == "WorksheetModel"


class TestIgnoresPureLinkLines:
    """Lines that are pure markdown links are NOT flagged."""

    def test_bare_link_line(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            [WorksheetModel](https://example.com/WorksheetModel)
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 0, f"Pure link line should not be flagged, got {hits}"

    def test_list_link_line(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            - [WorksheetModel](https://example.com/api/WorksheetModel)
            * [WorkbookModel](/api/WorkbookModel)
        """)
        patterns = _patterns(["WorksheetModel", "WorkbookModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 0, f"List link lines should not be flagged, got {hits}"

    def test_prose_with_inline_link_is_flagged(self, tmp_path: Path):
        """A prose sentence that contains a link is still checked."""
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            See the [WorksheetModel](https://example.com) class for details on sheets.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        # This line is prose (not a pure link) so it SHOULD be flagged
        assert len(hits) == 1, (
            f"Prose line with inline link should still be flagged, got {hits}"
        )


class TestNoFalsePartialMatch:
    """Word-boundary matching prevents partial-name false positives."""

    def test_workbook_does_not_match_workbook_designer(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            Use WorkbookDesigner to build template workbooks.
        """)
        patterns = _patterns(["Workbook"])
        hits = scan_file(md, patterns)
        # "Workbook" as a whole word does NOT appear; only "WorkbookDesigner" does
        assert len(hits) == 0, (
            f"'Workbook' should not match 'WorkbookDesigner', got {hits}"
        )

    def test_exact_name_match_works(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            Use the Workbook class directly.
        """)
        patterns = _patterns(["Workbook"])
        hits = scan_file(md, patterns)
        assert len(hits) == 1

    def test_worksheet_model_vs_worksheet(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            The Worksheet class manages sheet data.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) == 0, (
            f"'WorksheetModel' should not match 'Worksheet', got {hits}"
        )


class TestMachineReadableOutput:
    """scan_file output is valid JSON-serializable with expected keys."""

    REQUIRED_KEYS = {"file", "line_number", "api_name", "context_snippet",
                     "confidence", "finding"}

    def test_output_structure(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            The WorksheetModel class is stale.
        """)
        patterns = _patterns(["WorksheetModel"])
        hits = scan_file(md, patterns)
        assert len(hits) >= 1

        for hit in hits:
            # Must be JSON-serializable
            serialized = json.dumps(hit)
            recovered = json.loads(serialized)
            # Must have all required keys
            missing = self.REQUIRED_KEYS - set(recovered.keys())
            assert not missing, f"Hit missing keys {missing}: {recovered}"
            # Types
            assert isinstance(recovered["line_number"], int)
            assert isinstance(recovered["confidence"], float)
            assert recovered["finding"] == "PROSE_STALE_API_REF"

    def test_empty_output_when_no_hits(self, tmp_path: Path):
        md = _write_tmp_md(tmp_path, """\
            ---
            title: Test
            ---

            This page has no references to removed APIs.
        """)
        patterns = _patterns(["WorksheetModel", "WorkbookModel"])
        hits = scan_file(md, patterns)
        assert hits == []
        # Also verifiable as JSON
        assert json.dumps(hits) == "[]"


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestHelperFunctions:

    def test_strip_frontmatter_basic(self):
        lines = ["---", "title: Test", "---", "Body line"]
        body, start = _strip_frontmatter(lines)
        assert body == ["Body line"]
        assert start == 4

    def test_strip_frontmatter_no_frontmatter(self):
        lines = ["Body line", "Another line"]
        body, start = _strip_frontmatter(lines)
        assert body == lines
        assert start == 1

    def test_is_pure_link_line_bare(self):
        assert _is_pure_link_line("[Some Text](https://example.com)")

    def test_is_pure_link_line_list_item(self):
        assert _is_pure_link_line("- [Some Text](https://example.com)")
        assert _is_pure_link_line("* [Some Text](https://example.com)")

    def test_is_pure_link_line_prose(self):
        assert not _is_pure_link_line("See [the docs](https://example.com) for more.")

    def test_build_patterns_word_boundary(self):
        patterns = build_patterns(["WorksheetModel"])
        pat = patterns["WorksheetModel"]
        assert pat.search("WorksheetModel")
        assert pat.search("use WorksheetModel in")
        assert not pat.search("WorksheetModelExtended")
        assert not pat.search("ExtendedWorksheetModel")
