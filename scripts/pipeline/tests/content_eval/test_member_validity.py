"""Regression tests for MemberValidityEvaluator (EV-03/EV-04).

Proven blind spot:
  A reference page with hallucinated property names (absent from api_surface)
  was earning grade B while containing properties that would raise AttributeError
  at runtime (e.g., Image.Width instead of Image.OriginalWidth).

Coverage:
1. Hallucinated property in property table → FAIL [MV]
2. Real property in property table → no finding
3. Class with no properties in api_surface → no finding (can't validate)
4. Non-reference page → no finding (evaluator is scoped to reference subdomain)
5. Inherited-section rows are not flagged
6. MV FAIL grade ceiling caps at C (models layer)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from content_eval.models import Page, compute_grade_with_criticality
from content_eval.evaluators.member_validity import MemberValidityEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ref_page(tmp_path: Path, body: str, class_name: str = "Widget") -> Page:
    """Write a reference page to a temp path with the standard tree structure."""
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "python"
    ref_dir.mkdir(parents=True, exist_ok=True)
    md_file = ref_dir / f"{class_name}.md"
    frontmatter = (
        f"---\ntitle: {class_name}\nlinktitle: {class_name}\n"
        "categories:\n- Class\nlayout: single\n"
        "provenance:\n  content_origin: skill-generated\n"
        "  last_mechanism: unknown\n  auto_updatable: true\n---\n\n"
    )
    md_file.write_text(frontmatter + body, encoding="utf-8")
    return Page.load(md_file)


def _api_surface_for(class_name: str, props: list[str], methods: list[str] = ()) -> list[dict]:
    return [{
        "name": class_name,
        "properties": [{"name": p} for p in props],
        "methods": [{"name": m} for m in methods],
        "enum_members": [],
    }]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestMemberValidityEvaluator:

    def test_hallucinated_property_produces_fail(self, tmp_path):
        """Proven defect: property absent from api_surface → FAIL [MV]."""
        body = (
            "## Properties\n\n"
            "| Property | Type | Access | Description |\n"
            "|----------|------|--------|-------------|\n"
            "| `RealProp` | `str` | Read | A real property |\n"
            "| `FakeProp` | `str` | Read | A hallucinated property |\n"
        )
        page = _make_ref_page(tmp_path, body, "Widget")
        api = _api_surface_for("Widget", props=["RealProp"])

        evaluator = MemberValidityEvaluator()
        with patch.object(evaluator, "_load_api_surface", return_value=api):
            findings = evaluator.evaluate(page, None)

        mv_fails = [f for f in findings if f.category == "MV" and f.level == "FAIL"]
        assert len(mv_fails) == 1
        assert "FakeProp" in mv_fails[0].message
        assert "RealProp" not in mv_fails[0].message

    def test_real_property_produces_no_finding(self, tmp_path):
        """True negative: all properties present in api_surface → no MV finding."""
        body = (
            "## Properties\n\n"
            "| Property | Type | Access | Description |\n"
            "|----------|------|--------|-------------|\n"
            "| `Alpha` | `str` | Read | |\n"
            "| `Beta` | `int` | Read | |\n"
        )
        page = _make_ref_page(tmp_path, body, "Widget")
        api = _api_surface_for("Widget", props=["Alpha", "Beta"])

        evaluator = MemberValidityEvaluator()
        with patch.object(evaluator, "_load_api_surface", return_value=api):
            findings = evaluator.evaluate(page, None)

        mv = [f for f in findings if f.category == "MV"]
        assert mv == []

    def test_class_with_no_api_surface_members_is_skipped(self, tmp_path):
        """When class has 0 known members (model incomplete), evaluator is silent."""
        body = (
            "## Properties\n\n"
            "| Property | Type | Access | Description |\n"
            "|----------|------|--------|-------------|\n"
            "| `SomeProperty` | `str` | Read | |\n"
        )
        page = _make_ref_page(tmp_path, body, "Widget")
        # Class found but has no properties/methods
        api = [{"name": "Widget", "properties": [], "methods": [], "enum_members": []}]

        evaluator = MemberValidityEvaluator()
        with patch.object(evaluator, "_load_api_surface", return_value=api):
            findings = evaluator.evaluate(page, None)

        mv = [f for f in findings if f.category == "MV"]
        assert mv == []

    def test_non_reference_page_is_skipped(self, tmp_path):
        """Evaluator does not run on non-reference subdomains."""
        docs_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "test" / "python"
        docs_dir.mkdir(parents=True, exist_ok=True)
        md_file = docs_dir / "index.md"
        md_file.write_text(
            "---\ntitle: Test\nlinktitle: Widget\n"
            "provenance:\n  content_origin: skill-generated\n"
            "  last_mechanism: unknown\n  auto_updatable: true\n---\n\n"
            "## Properties\n\n"
            "| Property | Type | Access | Description |\n"
            "|----------|------|--------|-------------|\n"
            "| `FakeProp` | `str` | Read | |\n",
            encoding="utf-8",
        )
        page = Page.load(md_file)
        assert page.subdomain != "reference"
        api = _api_surface_for("Widget", props=["RealProp"])

        evaluator = MemberValidityEvaluator()
        with patch.object(evaluator, "_load_api_surface", return_value=api):
            findings = evaluator.evaluate(page, None)

        mv = [f for f in findings if f.category == "MV"]
        assert mv == []

    def test_inherited_section_rows_are_not_flagged(self, tmp_path):
        """Property rows under an 'Inherited from …' heading are skipped."""
        body = (
            "## Properties\n\n"
            "| Property | Type | Access | Description |\n"
            "|----------|------|--------|-------------|\n"
            "| `OwnProp` | `str` | Read | Own property |\n"
            "\n"
            "### Inherited from BaseClass\n\n"
            "| Property | Type | Access | Description |\n"
            "|----------|------|--------|-------------|\n"
            "| `InheritedProp` | `str` | Read | Not owned by Widget |\n"
        )
        page = _make_ref_page(tmp_path, body, "Widget")
        api = _api_surface_for("Widget", props=["OwnProp"])

        evaluator = MemberValidityEvaluator()
        with patch.object(evaluator, "_load_api_surface", return_value=api):
            findings = evaluator.evaluate(page, None)

        mv = [f for f in findings if f.category == "MV"]
        assert mv == [], f"Expected no MV findings (InheritedProp is in inherited section), got: {mv}"

    def test_mv_fail_grade_ceiling_caps_at_c(self):
        """MV (member_validity) is EXPERIMENTAL — its FAIL must NOT cap canonical grade.

        After FA-01 canonical/experimental separation, member_validity findings are
        excluded from compute_grade_with_criticality(). A page with only an MV FAIL
        from member_validity must receive canonical grade A (no canonical findings).
        The MV ceiling in grade_config.yaml is intentionally inactive for this
        EXPERIMENTAL evaluator until it graduates to the canonical set.
        """
        from content_eval.models import Finding

        findings_with_mv_fail = [
            Finding(
                level="FAIL",
                category="MV",
                filepath="test.md",
                line_no=10,
                message="Property `FakeProp` not in api_surface",
                evaluator="member_validity",
            )
        ]
        grade = compute_grade_with_criticality(findings_with_mv_fail)
        assert grade == "A", (
            f"member_validity is EXPERIMENTAL — its FAIL must not cap canonical grade; got {grade}"
        )

    def test_mv_fail_does_not_force_f(self):
        """MV FAIL is a ceiling (C), not a critical category (F)."""
        from content_eval.models import Finding, CRITICAL_CATEGORIES

        assert "MV" not in CRITICAL_CATEGORIES
        findings = [
            Finding(
                level="FAIL",
                category="MV",
                filepath="test.md",
                line_no=10,
                message="MV fail",
                evaluator="member_validity",
            )
        ]
        grade = compute_grade_with_criticality(findings)
        assert grade != "F", "MV FAIL should not force grade F"
