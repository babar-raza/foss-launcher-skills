"""Unit tests for ApiCompletenessEvaluator (H-12).

Coverage:
1. _UNIVERSAL_SKIP members (constructor, toString, etc.) are not counted as missing
2. Section headers (### MethodName()) are recognised as documented members
3. Backtick references with parens (`getValue()`) are recognised as documented
4. >30% missing → FAIL
5. <10% missing → no finding
6. 10-30% missing → WARN

All tests use real temp files (pytest tmp_path) so that page.filepath.read_text()
works correctly, and patch _load_api_surface to inject controlled api_surface data.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from content_eval.models import Page
from content_eval.evaluators.api_completeness import ApiCompletenessEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ref_page(tmp_path: Path, body: str, class_name: str) -> Page:
    """Write a markdown reference page under a fake reference.aspose.org tree.

    The path encodes family='pdf', platform='java' so that Page.load() infers
    subdomain='reference', family='pdf', platform='java'.
    """
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "java"
    ref_dir.mkdir(parents=True, exist_ok=True)
    md_file = ref_dir / f"{class_name}.md"
    frontmatter = f"---\ntitle: {class_name}\nlinkTitle: {class_name}\n---\n\n"
    md_file.write_text(frontmatter + body, encoding="utf-8")
    return Page.load(md_file)


def _api_surface_with(class_name: str, methods: list[str], properties: list[str]) -> list[dict]:
    """Return a minimal api_surface list with one class entry."""
    return [
        {
            "name": class_name,
            "methods": [{"name": m} for m in methods],
            "properties": [{"name": p} for p in properties],
        }
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUniversalSkip:
    """_UNIVERSAL_SKIP members must not be counted as missing."""

    def test_universal_skip_not_counted_as_missing(self, tmp_path):
        """Class with only constructor + toString; page body mentions neither.

        Expected: 0 findings (both are in _UNIVERSAL_SKIP → expected_members is
        empty → evaluator returns [] before reaching threshold logic).
        """
        class_name = "MyClass"
        page = _make_ref_page(tmp_path, body="Some prose.\n", class_name=class_name)

        api_data = _api_surface_with(
            class_name,
            methods=["constructor", "toString"],
            properties=[],
        )

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"Universal-skip members should not be counted as missing, got: {findings}"
        )


class TestSectionHeaderDetection:
    """_SECTION_HEADER_RE must detect ### MethodName() as a documented member."""

    def test_section_header_detected_as_documented(self, tmp_path):
        """Page has ### GetBoundingBox() header; api_surface has GetBoundingBox.

        Expected: 0 findings because the section header satisfies the member.
        """
        class_name = "BoundingBoxClass"
        body = "## Overview\n\nSome description.\n\n### GetBoundingBox()\n\nReturns the bounding box.\n"
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)

        api_data = _api_surface_with(
            class_name,
            methods=["GetBoundingBox"],
            properties=[],
        )

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"Section header '### GetBoundingBox()' should document the method, got: {findings}"
        )


class TestBacktickWithParens:
    """`_BACKTICK_MEMBER_RE` must match `method()` as well as `member`."""

    def test_backtick_with_parens_detected(self, tmp_path):
        """Page has `getValue()` in a table cell; api_surface has getValue.

        Expected: 0 findings because backtick+parens satisfies the member.
        """
        class_name = "ValueClass"
        body = (
            "## Methods\n\n"
            "| Method | Description |\n"
            "|--------|-------------|\n"
            "| `getValue()` | Returns the current value. |\n"
        )
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)

        api_data = _api_surface_with(
            class_name,
            methods=["getValue"],
            properties=[],
        )

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"`getValue()` in a table cell should be recognised as documenting getValue, got: {findings}"
        )


class TestMissingMembersFail:
    """0 of 5 expected members documented → FAIL."""

    def test_missing_members_triggers_fail(self, tmp_path):
        class_name = "ShapeClass"
        # Page body has no mention of any of the 5 expected methods
        body = "This page is about ShapeClass.\n"
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)

        methods = ["getWidth", "getHeight", "getArea", "getPerimeter", "clone"]
        api_data = _api_surface_with(class_name, methods=methods, properties=[])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1, f"Expected exactly 1 finding, got: {findings}"
        assert findings[0].level == "FAIL", (
            f"0/5 documented (100% missing) should be FAIL, got level={findings[0].level}"
        )
        assert findings[0].category == "AC"


class TestBelowThreshold:
    """9 of 10 expected members documented (10% missing) → no finding."""

    def test_below_threshold_no_finding(self, tmp_path):
        class_name = "RectangleClass"
        methods = [f"method{i}" for i in range(10)]  # method0 … method9

        # Document 9 of 10 via section headers (method0 … method8)
        headers = "\n".join(f"### {m}()\n\nDoes something.\n" for m in methods[:9])
        body = f"## Overview\n\n{headers}\n"
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)

        api_data = _api_surface_with(class_name, methods=methods, properties=[])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"9/10 documented (10% missing) should produce no finding, got: {findings}"
        )


class TestWarnBetween10And30Percent:
    """7 of 10 expected members documented (30% missing) → WARN."""

    def test_warn_between_10_and_30_percent(self, tmp_path):
        class_name = "EllipseClass"
        methods = [f"method{i}" for i in range(10)]  # method0 … method9

        # Document 7 of 10 via section headers (method0 … method6)
        headers = "\n".join(f"### {m}()\n\nDoes something.\n" for m in methods[:7])
        body = f"## Overview\n\n{headers}\n"
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)

        api_data = _api_surface_with(class_name, methods=methods, properties=[])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1, f"Expected exactly 1 finding, got: {findings}"
        assert findings[0].level == "WARN", (
            f"3/10 missing (30%) should be WARN, got level={findings[0].level}"
        )
        assert findings[0].category == "AC"
