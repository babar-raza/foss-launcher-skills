"""Test that content-eval grade gate downgrades gap-eval verdict.

T-12: When a finding references a file with grade D or F in frontmatter,
compute_verdict should return CONDITIONAL instead of PUBLICATION READY.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Ensure gap-eval is importable
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))


def _make_page_with_grade(tmp_path: Path, grade: str) -> Path:
    """Create a minimal markdown file with a grade in frontmatter."""
    md = tmp_path / "content" / "test" / "_index.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(textwrap.dedent(f"""\
        ---
        title: "Test Page"
        grade: {grade}
        graded_logic_version: "8"
        ---

        Content here.
    """), encoding="utf-8")
    return md


class TestVerdictGate:
    """Content-eval grade gate tests."""

    def test_grade_d_downgrades_verdict(self, tmp_path):
        """A finding on a grade-D file should downgrade to CONDITIONAL."""
        from run import compute_verdict

        page = _make_page_with_grade(tmp_path, "D")
        findings = [
            {"file": str(page), "severity": "L", "status": "open", "tier_resolved_by": 1}
        ]
        verdict = compute_verdict(findings)
        assert "CONDITIONAL" in verdict, f"Expected CONDITIONAL, got: {verdict}"

    def test_grade_f_downgrades_verdict(self, tmp_path):
        """A finding on a grade-F file should downgrade to CONDITIONAL."""
        from run import compute_verdict

        page = _make_page_with_grade(tmp_path, "F")
        findings = [
            {"file": str(page), "severity": "L", "status": "open", "tier_resolved_by": 1}
        ]
        verdict = compute_verdict(findings)
        assert "CONDITIONAL" in verdict, f"Expected CONDITIONAL, got: {verdict}"

    def test_grade_a_stays_publication_ready(self, tmp_path):
        """A finding on a grade-A file should not trigger the gate."""
        from run import compute_verdict

        page = _make_page_with_grade(tmp_path, "A")
        findings = [
            {"file": str(page), "severity": "L", "status": "open", "tier_resolved_by": 1}
        ]
        verdict = compute_verdict(findings)
        assert verdict == "PUBLICATION READY", f"Expected PUBLICATION READY, got: {verdict}"

    def test_no_grade_stays_publication_ready(self, tmp_path):
        """A finding on a file with no grade should not trigger the gate."""
        from run import compute_verdict

        md = tmp_path / "content" / "test" / "_index.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text("---\ntitle: Test\n---\nContent.\n", encoding="utf-8")
        findings = [
            {"file": str(md), "severity": "L", "status": "open", "tier_resolved_by": 1}
        ]
        verdict = compute_verdict(findings)
        assert verdict == "PUBLICATION READY", f"Expected PUBLICATION READY, got: {verdict}"

    def test_nonexistent_file_stays_publication_ready(self):
        """A finding referencing a nonexistent file should not crash."""
        from run import compute_verdict

        findings = [
            {"file": "/nonexistent/path.md", "severity": "L", "status": "open", "tier_resolved_by": 1}
        ]
        verdict = compute_verdict(findings)
        assert verdict == "PUBLICATION READY", f"Expected PUBLICATION READY, got: {verdict}"

    def test_m_severity_still_blocks(self, tmp_path):
        """M-severity findings should still produce NOT PUBLISHABLE (higher priority)."""
        from run import compute_verdict

        page = _make_page_with_grade(tmp_path, "A")
        findings = [
            {"file": str(page), "severity": "M", "status": "open", "tier_resolved_by": 1}
        ]
        verdict = compute_verdict(findings)
        assert verdict == "NOT PUBLISHABLE", f"Expected NOT PUBLISHABLE, got: {verdict}"
