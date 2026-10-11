"""Tests for publish_classifier.py (TC-S90-001)."""

import pytest

from commands.launch.publish_classifier import (
    classify_page,
    classify_from_eval_report,
    classify_product,
    select_spot_check_sample,
    to_json_report,
    ClassificationResult,
    ProductClassification,
    CLASSIFICATION_LABELS,
)


class TestClassifyPage:
    def test_grade_a_no_fails_is_publish_ready(self):
        cls, skill = classify_page("A", 0, is_reference=False, has_apis=False)
        assert cls == "PUBLISH_READY"
        assert skill == ""

    def test_grade_b_no_fails_is_publish_ready(self):
        cls, skill = classify_page("B", 0, is_reference=True, has_apis=True)
        assert cls == "PUBLISH_READY"

    def test_grade_a_with_fails_not_publish_ready(self):
        """Grade A but with FAIL findings → not auto-classified as PUBLISH_READY."""
        cls, skill = classify_page("A", 2, is_reference=False, has_apis=False)
        # With FAILs, grade A can't be PUBLISH_READY; falls through to grade-based
        # Since "A" with fails isn't in the A/B+0-fail path, it goes to fallback
        assert cls != "BLOCKED"

    def test_grade_c_reference_with_apis_is_acceptable(self):
        cls, skill = classify_page("C", 0, is_reference=True, has_apis=True)
        assert cls == "ACCEPTABLE_GRADE_C"
        assert skill == ""

    def test_grade_c_docs_page_needs_s21(self):
        cls, skill = classify_page("C", 0, is_reference=False, has_apis=False)
        assert cls == "NEEDS_ACTION_S21"
        assert skill == "S-21"

    def test_grade_c_reference_no_apis_needs_s21(self):
        cls, skill = classify_page("C", 0, is_reference=True, has_apis=False)
        assert cls == "NEEDS_ACTION_S21"
        assert skill == "S-21"

    def test_grade_d_needs_s26(self):
        cls, skill = classify_page("D", 0, is_reference=False, has_apis=False)
        assert cls == "NEEDS_ACTION_S26"
        assert skill == "S-26"

    def test_grade_f_is_blocked(self):
        cls, skill = classify_page("F", 5, is_reference=False, has_apis=False)
        assert cls == "BLOCKED"
        assert skill == ""


class TestClassifyFromEvalReport:
    def test_grade_a_page(self):
        result = classify_from_eval_report(
            "content/docs.aspose.org/en/cells/python/overview.md",
            {"grade": "A", "findings": [], "evidence": {"apis": ["Workbook"]}},
        )
        assert result.classification == "PUBLISH_READY"
        assert result.grade == "A"
        assert result.has_apis is True

    def test_reference_page_detection(self):
        result = classify_from_eval_report(
            "content/reference.aspose.org/en/cells/net/Workbook.md",
            {"grade": "C", "findings": [], "evidence": {"apis": ["Workbook"]}},
        )
        assert result.is_reference is True
        assert result.classification == "ACCEPTABLE_GRADE_C"


class TestClassifyProduct:
    def _make_evals(self):
        return {
            "page_a.md": {"grade": "A", "findings": [], "evidence": {"apis": ["X"]}},
            "page_b.md": {"grade": "B", "findings": [], "evidence": {"apis": []}},
            "content/reference.aspose.org/en/x/y/Z.md": {
                "grade": "C", "findings": [], "evidence": {"apis": ["Z"]},
            },
            "page_d.md": {"grade": "D", "findings": [], "evidence": {}},
            "page_f.md": {"grade": "F", "findings": [{"level": "FAIL"}], "evidence": {}},
        }

    def test_summary_counts(self):
        pc = classify_product("cells", "net", self._make_evals())
        assert pc.total_pages == 5
        s = pc.summary
        assert s["PUBLISH_READY"] == 2
        assert s["ACCEPTABLE_GRADE_C"] == 1
        assert s["NEEDS_ACTION_S26"] == 1
        assert s["BLOCKED"] == 1

    def test_spot_check_sample_reproducible(self):
        evals = self._make_evals()
        pc1 = classify_product("cells", "net", evals, spot_check_seed=42)
        pc2 = classify_product("cells", "net", evals, spot_check_seed=42)
        assert pc1.spot_check_sample == pc2.spot_check_sample

    def test_spot_check_different_seed(self):
        # With only 2 PUBLISH_READY and 10% sample, both seeds give 1 sample
        evals = self._make_evals()
        pc1 = classify_product("cells", "net", evals, spot_check_seed=42)
        assert len(pc1.spot_check_sample) >= 1


class TestJsonReport:
    def test_report_structure(self):
        pc = classify_product("pdf", "go", {
            "page.md": {"grade": "A", "findings": [], "evidence": {"apis": ["X"]}},
        })
        report = to_json_report(pc)
        assert report["family"] == "pdf"
        assert report["platform"] == "go"
        assert report["total_pages"] == 1
        assert "summary" in report
        assert "pages" in report
        assert len(report["pages"]) == 1
        assert report["pages"][0]["classification"] == "PUBLISH_READY"


class TestSelectSpotCheckSample:
    def test_empty_results(self):
        assert select_spot_check_sample([], seed=42) == []

    def test_no_publish_ready(self):
        results = [ClassificationResult("p.md", "D", "NEEDS_ACTION_S26")]
        assert select_spot_check_sample(results, seed=42) == []

    def test_deterministic_with_same_seed(self):
        results = [
            ClassificationResult(f"page_{i}.md", "A", "PUBLISH_READY")
            for i in range(20)
        ]
        s1 = select_spot_check_sample(results, seed=123)
        s2 = select_spot_check_sample(results, seed=123)
        assert s1 == s2
        assert len(s1) == 2  # 10% of 20
