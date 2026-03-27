"""Remediation planner — groups findings into prioritized fix batches."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..models import EvalReport, Finding


@dataclass
class RemediationBatch:
    """A batch of related fixes to apply together."""

    priority: int
    description: str
    files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    estimated_effort: str = "low"  # low, medium, high
    post_actions: list[str] = field(default_factory=list)


def plan_remediation(report: EvalReport) -> list[RemediationBatch]:
    """Generate prioritized remediation batches from evaluation report."""
    batches: list[RemediationBatch] = []

    by_file = report.by_file()
    by_category = report.by_category()

    # Priority 1: FAIL findings grouped by file
    fail_files: dict[str, list[Finding]] = defaultdict(list)
    for f in report.fails:
        fail_files[f.filepath].append(f)

    if fail_files:
        batches.append(RemediationBatch(
            priority=1,
            description=f"Fix {len(report.fails)} FAIL findings across {len(fail_files)} files",
            files=sorted(fail_files.keys()),
            findings=report.fails,
            estimated_effort="medium" if len(report.fails) > 10 else "low",
            post_actions=["Run attach_evidence.py", "Run audit.py to verify"],
        ))

    # Priority 2: Platform contamination warnings
    pc_findings = by_category.get("PC", [])
    pc_warns = [f for f in pc_findings if f.level == "WARN"]
    if pc_warns:
        pc_files = sorted(set(f.filepath for f in pc_warns))
        batches.append(RemediationBatch(
            priority=2,
            description=f"Review {len(pc_warns)} platform contamination warnings",
            files=pc_files,
            findings=pc_warns,
            estimated_effort="low",
        ))

    # Priority 3: Role violation warnings
    rv_findings = by_category.get("RV", [])
    rv_warns = [f for f in rv_findings if f.level in ("FAIL", "WARN")]
    if rv_warns:
        rv_files = sorted(set(f.filepath for f in rv_warns))
        batches.append(RemediationBatch(
            priority=3,
            description=f"Fix {len(rv_warns)} role/structure violations",
            files=rv_files,
            findings=rv_warns,
            estimated_effort="medium",
        ))

    # Priority 4: Evidence gaps
    eg_findings = by_category.get("EG", [])
    if eg_findings:
        eg_files = sorted(set(f.filepath for f in eg_findings))
        batches.append(RemediationBatch(
            priority=4,
            description=f"Address {len(eg_findings)} evidence gaps",
            files=eg_files,
            findings=eg_findings,
            estimated_effort="low",
            post_actions=["Run attach_evidence.py"],
        ))

    return batches
