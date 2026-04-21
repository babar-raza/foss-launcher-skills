"""Tests for refresh_review.py — per-page decision logging and coverage reporting.

Coverage:
- record_decision(): writes correct JSON with decision/reason/body_hash_changed
- record_decision(): invalid decision raises ValueError
- record_decision(): multiple calls accumulate correctly (dedup by path)
- generate_coverage_report(): counts per subdomain correctly
- generate_coverage_report(): writes coverage_report.md
- generate_coverage_report(): handles empty decisions gracefully
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import refresh_review


# ---------------------------------------------------------------------------
# record_decision tests
# ---------------------------------------------------------------------------

class TestRecordDecision:
    def test_writes_correct_json(self, tmp_path):
        """Three decisions recorded; page_decisions.json has 3 entries with correct fields."""
        refresh_review.record_decision(
            "cells", "net",
            path="content/docs.aspose.org/en/cells/net/page1.md",
            decision="BODY_UPDATED",
            reason="modified_claims CLM-cells-001 cited in paragraph 3",
            body_hash_changed=True,
            review_root=tmp_path,
        )
        refresh_review.record_decision(
            "cells", "net",
            path="content/docs.aspose.org/en/cells/net/page2.md",
            decision="EVIDENCE_ONLY",
            reason="PIA score NOT_AFFECTED; no delta signals in body",
            review_root=tmp_path,
        )
        refresh_review.record_decision(
            "cells", "net",
            path="content/kb.aspose.org/en/cells/net/faq.md",
            decision="NOT_AFFECTED",
            reason="PIA score NOT_AFFECTED",
            review_root=tmp_path,
        )

        p = tmp_path / "cells" / "net" / "page_decisions.json"
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        pages = data["pages"]

        assert len(pages) == 3
        p1 = pages["content/docs.aspose.org/en/cells/net/page1.md"]
        assert p1["decision"] == "BODY_UPDATED"
        assert p1["body_hash_changed"] is True
        assert "CLM-cells-001" in p1["reason"]

        p2 = pages["content/docs.aspose.org/en/cells/net/page2.md"]
        assert p2["decision"] == "EVIDENCE_ONLY"
        assert p2["body_hash_changed"] is False

    def test_invalid_decision_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid decision"):
            refresh_review.record_decision(
                "cells", "net",
                path="content/docs.aspose.org/en/cells/net/page.md",
                decision="UNKNOWN_DECISION",
                reason="test",
                review_root=tmp_path,
            )

    def test_overwrite_existing_path(self, tmp_path):
        """Recording a decision for an existing path overwrites it."""
        path = "content/docs.aspose.org/en/cells/net/page.md"
        refresh_review.record_decision("cells", "net", path=path,
            decision="EVIDENCE_ONLY", reason="first", review_root=tmp_path)
        refresh_review.record_decision("cells", "net", path=path,
            decision="BODY_UPDATED", reason="second", review_root=tmp_path)

        p = tmp_path / "cells" / "net" / "page_decisions.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["pages"][path]["decision"] == "BODY_UPDATED"
        assert data["pages"][path]["reason"] == "second"

    def test_all_valid_decisions_accepted(self, tmp_path):
        for i, decision in enumerate(sorted(refresh_review.VALID_DECISIONS)):
            refresh_review.record_decision(
                "fam", "plat",
                path=f"content/docs.aspose.org/en/fam/plat/page{i}.md",
                decision=decision,
                reason="test",
                review_root=tmp_path,
            )

    def test_retired_decision_accepted(self, tmp_path):
        refresh_review.record_decision(
            "cells", "net",
            path="content/blog.aspose.org/cells/net/old-post.md",
            decision="RETIRED",
            reason="page in pages_to_remove; removed_api cited",
            review_root=tmp_path,
        )
        p = tmp_path / "cells" / "net" / "page_decisions.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["pages"]["content/blog.aspose.org/cells/net/old-post.md"]["decision"] == "RETIRED"


# ---------------------------------------------------------------------------
# generate_coverage_report tests
# ---------------------------------------------------------------------------

class TestGenerateCoverageReport:
    def _seed_decisions(self, tmp_path: Path) -> None:
        """Write a set of decisions spanning multiple subdomains."""
        decisions = [
            ("content/docs.aspose.org/en/cells/net/page1.md", "BODY_UPDATED"),
            ("content/docs.aspose.org/en/cells/net/page2.md", "EVIDENCE_ONLY"),
            ("content/docs.aspose.org/en/cells/net/page3.md", "NOT_AFFECTED"),
            ("content/kb.aspose.org/en/cells/net/faq.md", "BODY_UPDATED"),
            ("content/kb.aspose.org/en/cells/net/howto.md", "EVIDENCE_ONLY"),
            ("content/blog.aspose.org/cells/net/post.md", "RETIRED"),
            ("content/products.aspose.org/en/cells/net/_index.md", "EVIDENCE_ONLY"),
            ("content/reference.aspose.org/en/cells/net/Workbook.md", "BODY_UPDATED"),
            ("content/reference.aspose.org/en/cells/net/Cells.md", "BODY_UPDATED"),
        ]
        for path, decision in decisions:
            refresh_review.record_decision(
                "cells", "net", path=path, decision=decision,
                reason="test", review_root=tmp_path
            )

    def test_report_counts_per_subdomain_correct(self, tmp_path):
        """Coverage report table rows match seeded decision fixture counts."""
        self._seed_decisions(tmp_path)
        report = refresh_review.generate_coverage_report("cells", "net", review_root=tmp_path)

        # docs: 3 total (1 BODY_UPDATED, 1 EVIDENCE_ONLY, 1 NOT_AFFECTED)
        assert "| docs | 3 |" in report
        # kb: 2 total (1 BODY_UPDATED, 1 EVIDENCE_ONLY)
        assert "| kb | 2 |" in report
        # blog: 1 RETIRED
        assert "| blog | 1 |" in report
        # products: 1 EVIDENCE_ONLY
        assert "| products | 1 |" in report
        # reference: 2 BODY_UPDATED
        assert "| reference | 2 |" in report

    def test_coverage_report_md_written(self, tmp_path):
        """generate_coverage_report() writes coverage_report.md."""
        self._seed_decisions(tmp_path)
        refresh_review.generate_coverage_report("cells", "net", review_root=tmp_path)

        report_path = tmp_path / "cells" / "net" / "coverage_report.md"
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "# Coverage Report: cells/net" in content

    def test_empty_decisions_produces_empty_report(self, tmp_path):
        """When no decisions recorded, report has totals of 0."""
        report = refresh_review.generate_coverage_report("cells", "net", review_root=tmp_path)
        assert "Total pages decided: 0" in report

    def test_total_row_sums_correctly(self, tmp_path):
        """TOTAL row counts match sum of all per-subdomain rows."""
        self._seed_decisions(tmp_path)
        report = refresh_review.generate_coverage_report("cells", "net", review_root=tmp_path)
        # 9 total pages seeded
        assert "**9**" in report or "| **TOTAL** | **9**" in report
