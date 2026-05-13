"""Tests for healing classifier and verifier — TC-04."""
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from healing.detector import HealingFinding, IssueType, Severity
from healing.classifier import classify, ClassifiedFinding
from healing.verifier import verify_finding, VerifyStatus, MAX_HEAL_DEPTH


class TestClassify:

    def test_missing_page_auto_remediable(self):
        finding = HealingFinding(
            issue_type=IssueType.MISSING_PAGE,
            severity=Severity.CRITICAL,
            entity="Font",
            detail="Class Font missing",
        )
        classified = classify([finding])
        assert len(classified) == 1
        assert classified[0].auto_remediable is True
        assert "batch_reference" in classified[0].remediation_tool

    def test_format_contradiction_not_auto_remediable(self):
        finding = HealingFinding(
            issue_type=IssueType.FORMAT_CONTRADICTION,
            severity=Severity.HIGH,
            entity="Font",
            detail="Format mismatch",
        )
        classified = classify([finding])
        assert classified[0].auto_remediable is False

    def test_stale_page_auto_remediable(self):
        finding = HealingFinding(
            issue_type=IssueType.STALE_PAGE,
            severity=Severity.HIGH,
            entity="Font",
            detail="SHA mismatch",
        )
        classified = classify([finding])
        assert classified[0].auto_remediable is True

    def test_silent_omission_not_auto_remediable(self):
        finding = HealingFinding(
            issue_type=IssueType.SILENT_OMISSION,
            severity=Severity.MEDIUM,
            entity="MyClass",
            detail="Public class filtered",
        )
        classified = classify([finding])
        assert classified[0].auto_remediable is False
        assert "human review" in classified[0].remediation_tool

    def test_metadata_corruption_auto_remediable(self):
        finding = HealingFinding(
            issue_type=IssueType.METADATA_CORRUPTION,
            severity=Severity.HIGH,
            entity="Font",
            detail="Missing evidence",
        )
        classified = classify([finding])
        assert classified[0].auto_remediable is True

    def test_empty_input(self):
        assert classify([]) == []

    def test_multiple_findings(self):
        findings = [
            HealingFinding(IssueType.MISSING_PAGE, Severity.CRITICAL, "A", ""),
            HealingFinding(IssueType.STALE_PAGE, Severity.HIGH, "B", ""),
            HealingFinding(IssueType.FORMAT_CONTRADICTION, Severity.HIGH, "C", ""),
        ]
        classified = classify(findings)
        assert len(classified) == 3
        auto_count = sum(1 for c in classified if c.auto_remediable)
        assert auto_count == 2  # MISSING_PAGE + STALE_PAGE


class TestVerifier:

    def test_verified_when_finding_resolved(self):
        finding = HealingFinding(IssueType.MISSING_PAGE, Severity.CRITICAL, "Font", "")

        def mock_detect(**kwargs):
            return []  # Finding resolved

        status = verify_finding(finding, mock_detect, {})
        assert status == VerifyStatus.VERIFIED

    def test_unresolved_when_finding_persists(self):
        finding = HealingFinding(IssueType.MISSING_PAGE, Severity.CRITICAL, "Font", "")

        def mock_detect(**kwargs):
            return [finding]  # Still present

        status = verify_finding(finding, mock_detect, {})
        assert status == VerifyStatus.UNRESOLVED

    def test_escalated_at_max_depth(self):
        finding = HealingFinding(IssueType.MISSING_PAGE, Severity.CRITICAL, "Font", "")

        def mock_detect(**kwargs):
            return [finding]

        status = verify_finding(finding, mock_detect, {}, heal_depth=MAX_HEAL_DEPTH)
        assert status == VerifyStatus.ESCALATED

    def test_verified_ignores_other_entities(self):
        finding = HealingFinding(IssueType.MISSING_PAGE, Severity.CRITICAL, "Font", "")

        def mock_detect(**kwargs):
            return [HealingFinding(IssueType.MISSING_PAGE, Severity.CRITICAL, "Other", "")]

        status = verify_finding(finding, mock_detect, {})
        assert status == VerifyStatus.VERIFIED  # "Font" is gone, "Other" is different
