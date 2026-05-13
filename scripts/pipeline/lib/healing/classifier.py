"""classifier.py — Assign remediation strategy to healing findings.

Each finding is classified with an auto_remediable flag and a
recommended remediation tool.

Usage:
    from healing.classifier import classify
    classified = classify(findings)
"""
from __future__ import annotations

from dataclasses import dataclass
from .detector import HealingFinding, IssueType, Severity


@dataclass
class ClassifiedFinding:
    finding: HealingFinding
    auto_remediable: bool
    remediation_tool: str
    notes: str = ""


# Mapping from issue type to (auto_remediable, tool, notes)
_STRATEGY = {
    IssueType.MISSING_PAGE: (True, "batch_reference single-class", ""),
    IssueType.STALE_PAGE: (True, "batch_reference --update", "Only if auto_updatable=true"),
    IssueType.HIERARCHY_DRIFT: (False, "template generation", "Requires manual review of _index.md content"),
    IssueType.SILENT_OMISSION: (False, "human review", "Review scope rules for correctness"),
    IssueType.GRADE_REGRESSION: (False, "re-evaluate + heal-page", "Conditional on root cause"),
    IssueType.METADATA_CORRUPTION: (True, "attach_evidence + safe_content_write", ""),
    IssueType.NAMING_DRIFT: (True, "file rename", ""),
    IssueType.FORMAT_CONTRADICTION: (False, "knowledge fix required", "Requires upstream knowledge correction"),
}


def classify(findings: list[HealingFinding]) -> list[ClassifiedFinding]:
    """Classify each finding with a remediation strategy."""
    result = []
    for f in findings:
        auto, tool, notes = _STRATEGY.get(
            f.issue_type,
            (False, "unknown", "No strategy defined"),
        )
        result.append(ClassifiedFinding(
            finding=f,
            auto_remediable=auto,
            remediation_tool=tool,
            notes=notes,
        ))
    return result
