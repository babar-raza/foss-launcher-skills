"""Tests for the duplicate_content evaluator (RC-W1-005, MT026 blind-spot audit).

Root cause: no evaluator in the content_eval registry detected duplicate or
near-duplicate *pages* (cross_page/deduplication.py only checks paragraphs,
and only runs opt-in via --cross-page). A real audit found 6 confirmed
duplicate-content page pairs on cells/net alone — identical title, identical
description/summary/claims/apis, near-identical body, with the newer page's
``aliases:`` frontmatter pointing at the older page's real live slug.

These tests cover:
  - the pure ``find_duplicate_pairs`` comparison (positive: near-identical
    pages + colliding alias -> FAIL/FAIL; negative: genuinely distinct pages
    on the same topic -> no findings)
  - slug computation + alias normalization (the primitives the alias-collision
    check depends on for correctness)
  - the full disk-scanning evaluator, proving the pair is flagged exactly
    once total across the whole batch (no duplicate findings when both pages
    in the pair are evaluated in the same run)
"""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from content_eval.models import Page
from content_eval.evaluators.duplicate_content import (
    DuplicateContentEvaluator,
    _compute_slug,
    _normalize_alias,
    _reset_caches,
    find_duplicate_pairs,
)

import content_discovery as _cd


def _make_page(content: str, filepath: str) -> Page:
    """Create a Page from markdown content string (same pattern as sibling evaluator tests)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


@pytest.fixture(autouse=True)
def _reset_module_caches():
    _reset_caches()
    yield
    _reset_caches()
    _cd.configure()


# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

_TITLE = "Key Features of Aspose.Cells FOSS for .NET"

_BODY_A = """\
## Introduction

Aspose.Cells FOSS for .NET is a pure managed-code, MIT-licensed library for reading, writing,
and manipulating Excel spreadsheets without any dependency on Microsoft Office. It gives .NET
developers a fast, dependency-free way to automate workbook creation, cell formatting, and data
validation directly from C# or VB.NET code, with no server-side Excel installation required.

## Workbook and Worksheet Lifecycle

Every automation task starts with creating or loading a Workbook, then navigating its collection
of Worksheets. The library exposes a simple, discoverable object model for adding sheets,
renaming them, and saving the final result back to disk in the XLSX format, all without touching
a single COM object or external process on the host machine.

## Styles, Validation, and Named Ranges

Beyond raw cell values, Aspose.Cells FOSS for .NET supports conditional formatting, data
validation rules, page setup for printing, and named ranges that make large workbooks easier to
navigate and maintain across teams working on the same spreadsheet.

## Get Started

Install the NuGet package and start building spreadsheet automation in minutes, no license key
and no Office installation required.
"""

# Near-identical to _BODY_A — only the closing sentence differs, matching the
# real defect's description: "only YAML-formatting and footer-link differences".
_BODY_B = """\
## Introduction

Aspose.Cells FOSS for .NET is a pure managed-code, MIT-licensed library for reading, writing,
and manipulating Excel spreadsheets without any dependency on Microsoft Office. It gives .NET
developers a fast, dependency-free way to automate workbook creation, cell formatting, and data
validation directly from C# or VB.NET code, with no server-side Excel installation required.

## Workbook and Worksheet Lifecycle

Every automation task starts with creating or loading a Workbook, then navigating its collection
of Worksheets. The library exposes a simple, discoverable object model for adding sheets,
renaming them, and saving the final result back to disk in the XLSX format, all without touching
a single COM object or external process on the host machine.

## Styles, Validation, and Named Ranges

Beyond raw cell values, Aspose.Cells FOSS for .NET supports conditional formatting, data
validation rules, page setup for printing, and named ranges that make large workbooks easier to
navigate and maintain across teams working on the same spreadsheet.

## Get Started

Grab the package from NuGet today and start automating Excel files in minutes.
"""

_BODY_CHARTS = """\
## Chart Types

Aspose.Cells FOSS for .NET can add column, line, pie, and scatter charts to a worksheet by
attaching a ChartType to a new Chart object placed at a specific cell range on the sheet.

## Adding a Chart to a Worksheet

A chart is created through the Worksheet's Charts collection, which accepts a chart type, an
anchor cell range for placement, and a data source range that supplies the series values.

## Customizing Series Colors and Legends

Individual data series expose fill color, marker style, and legend-entry text, letting callers
restyle a generated chart to match a report's branding without hand-editing the XML afterward.

## Exporting Chart Images

Once configured, a chart can be rendered directly to a PNG or JPEG image on disk, independent
of the rest of the workbook, which is useful for embedding chart previews in other documents.
"""

_BODY_CONDITIONAL = """\
## Rule Types

Conditional formatting in Aspose.Cells FOSS for .NET covers cell-value comparisons, formula-driven
rules, duplicate detection, and top/bottom ranking, each expressed as a FormatConditionType.

## Color Scales and Data Bars

Beyond simple highlight rules, color scales interpolate a cell's background across a gradient
based on its value, while data bars draw an in-cell bar whose length is proportional to the value.

## Icon Sets

Icon sets attach a small glyph — arrows, traffic lights, or flags — next to a cell based on which
threshold band its value falls into, giving a compact visual summary across a full column.

## Applying Rules Programmatically

Every rule type is added through the same FormatConditionCollection API, so a single code path
can apply value rules, color scales, and icon sets without special-casing each rule kind.
"""


def _frontmatter(title: str, aliases: str = "") -> str:
    alias_line = f"aliases: [{aliases}]\n" if aliases else ""
    return f"---\ntitle: {title}\n{alias_line}---\n"


# ---------------------------------------------------------------------------
# Pure function: find_duplicate_pairs
# ---------------------------------------------------------------------------

class TestFindDuplicatePairsPositive:
    """Two near-identical pages, one with an aliases entry colliding with the
    other's real live slug, must FAIL on both signals."""

    def _pages(self):
        page_a = _make_page(
            _frontmatter(_TITLE) + "\n" + _BODY_A,
            "content/blog.aspose.org/cells/net/cells-key-features-net/index.md",
        )
        page_b = _make_page(
            _frontmatter(_TITLE, aliases="/cells/net/cells-key-features-net/") + "\n" + _BODY_B,
            "content/blog.aspose.org/cells/net/dotnet-excel-formulas-charts/index.md",
        )
        return page_a, page_b

    def test_similarity_fail(self):
        page_a, page_b = self._pages()
        findings = find_duplicate_pairs([page_a, page_b])
        dp = [f for f in findings if f.category == "DP"]
        assert len(dp) == 1, f"expected exactly one DP finding, got: {findings}"
        assert dp[0].level == "FAIL"
        assert "dotnet-excel-formulas-charts" in dp[0].message or "cells-key-features-net" in dp[0].message

    def test_alias_collision_fail(self):
        page_a, page_b = self._pages()
        findings = find_duplicate_pairs([page_a, page_b])
        al = [f for f in findings if f.category == "AL"]
        assert len(al) == 1, f"expected exactly one AL finding, got: {findings}"
        assert al[0].level == "FAIL"
        # Attributed to the page that OWNS the colliding aliases: entry.
        assert al[0].filepath == str(page_b.filepath)
        assert "cells-key-features-net" in al[0].message

    def test_no_finding_duplication(self):
        """Each pair produces exactly one finding per signal — not one per page."""
        page_a, page_b = self._pages()
        findings = find_duplicate_pairs([page_a, page_b])
        assert len(findings) == 2, f"expected exactly 2 findings (1 DP + 1 AL), got: {findings}"


class TestFindDuplicatePairsNegative:
    """Two genuinely distinct pages on the same product/topic area must not
    be flagged — proves the evaluator doesn't cry wolf on legitimate content
    that merely shares vocabulary and product boilerplate."""

    def _pages(self):
        page_c = _make_page(
            _frontmatter("Building Charts in Excel Files with Aspose.Cells FOSS for .NET") + "\n" + _BODY_CHARTS,
            "content/blog.aspose.org/cells/net/dotnet-excel-charts-guide/index.md",
        )
        page_d = _make_page(
            _frontmatter("Conditional Formatting Rules in Aspose.Cells FOSS for .NET") + "\n" + _BODY_CONDITIONAL,
            "content/blog.aspose.org/cells/net/dotnet-excel-conditional-formatting/index.md",
        )
        return page_c, page_d

    def test_no_findings(self):
        page_c, page_d = self._pages()
        findings = find_duplicate_pairs([page_c, page_d])
        assert findings == [], f"distinct pages must not be flagged, got: {findings}"

    def test_single_page_group_no_findings(self):
        page_c, _ = self._pages()
        assert find_duplicate_pairs([page_c]) == []

    def test_empty_group_no_findings(self):
        assert find_duplicate_pairs([]) == []


# ---------------------------------------------------------------------------
# Slug computation + alias normalization primitives
# ---------------------------------------------------------------------------

class TestComputeSlug:
    def test_bundle_index_md(self):
        page = _make_page(
            "---\ntitle: T\n---\nBody.\n",
            "content/blog.aspose.org/cells/net/cells-key-features-net/index.md",
        )
        assert _compute_slug(page) == "/cells/net/cells-key-features-net/"

    def test_section_index_md_with_en(self):
        page = _make_page(
            "---\ntitle: T\n---\nBody.\n",
            "content/kb.aspose.org/en/cells/net/_index.md",
        )
        assert _compute_slug(page) == "/cells/net/"

    def test_leaf_md_renders_one_segment_deeper(self):
        page = _make_page(
            "---\ntitle: T\n---\nBody.\n",
            "content/kb.aspose.org/en/cells/net/how-to-configure-workbook-settings-dotnet.md",
        )
        assert _compute_slug(page) == "/cells/net/how-to-configure-workbook-settings-dotnet/"


class TestNormalizeAlias:
    def test_bare_path(self):
        assert _normalize_alias("/cells/net/cells-key-features-net/") == "/cells/net/cells-key-features-net/"

    def test_missing_slashes(self):
        assert _normalize_alias("cells/net/cells-key-features-net") == "/cells/net/cells-key-features-net/"

    def test_strips_scheme_and_host(self):
        assert (
            _normalize_alias("https://blog.aspose.org/cells/net/cells-key-features-net/")
            == "/cells/net/cells-key-features-net/"
        )

    def test_strips_leading_en(self):
        assert _normalize_alias("/en/cells/net/cells-key-features-net/") == "/cells/net/cells-key-features-net/"

    def test_empty(self):
        assert _normalize_alias("") == ""
        assert _normalize_alias(None) == ""


# ---------------------------------------------------------------------------
# Full evaluator — disk-scanning wiring + cross-page dedup-of-findings proof
# ---------------------------------------------------------------------------

class TestDuplicateContentEvaluatorDiskScan:
    def test_flags_pair_exactly_once_across_both_evaluate_calls(self, tmp_path):
        site_dir = tmp_path / "content" / "blog.aspose.org"
        page_a_dir = site_dir / "dupfam" / "net" / "cells-key-features-net"
        page_b_dir = site_dir / "dupfam" / "net" / "dotnet-excel-formulas-charts"
        page_a_dir.mkdir(parents=True)
        page_b_dir.mkdir(parents=True)
        (page_a_dir / "index.md").write_text(_frontmatter(_TITLE) + "\n" + _BODY_A, encoding="utf-8")
        (page_b_dir / "index.md").write_text(
            _frontmatter(_TITLE, aliases="/dupfam/net/cells-key-features-net/") + "\n" + _BODY_B,
            encoding="utf-8",
        )

        pattern = str(site_dir / "{family}/{platform}")
        evaluator = DuplicateContentEvaluator()

        with patch.object(_cd, "SITE_PATHS", [("blog.aspose.org", pattern)]):
            page_a = Page.load(page_a_dir / "index.md")
            page_a._infer_metadata()
            page_b = Page.load(page_b_dir / "index.md")
            page_b._infer_metadata()

            findings_a = evaluator.evaluate(page_a, None)
            findings_b = evaluator.evaluate(page_b, None)

        all_findings = findings_a + findings_b
        categories = sorted(f.category for f in all_findings)
        assert categories == ["AL", "DP"], f"expected exactly one AL + one DP finding total, got: {all_findings}"
        assert all(f.level == "FAIL" for f in all_findings)

    def test_non_blog_kb_subdomain_is_out_of_scope(self):
        page = _make_page(
            "---\ntitle: T\n---\nBody.\n",
            "content/docs.aspose.org/en/cells/net/getting-started.md",
        )
        assert DuplicateContentEvaluator().evaluate(page, None) == []

    def test_page_missing_family_platform_is_out_of_scope(self):
        page = _make_page("---\ntitle: T\n---\nBody.\n", "content/blog.aspose.org/orphan.md")
        assert DuplicateContentEvaluator().evaluate(page, None) == []
