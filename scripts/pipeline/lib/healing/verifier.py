"""verifier.py — Post-remediation verification loop.

Re-runs the original detector for a finding and checks if it is resolved.
Escalates after MAX_HEAL_DEPTH (3) failed attempts.

Usage:
    from healing.verifier import verify_finding
    status = verify_finding(finding, detect_fn, detect_kwargs)
"""
from __future__ import annotations

from enum import Enum
from typing import Callable

from .detector import HealingFinding, IssueType

MAX_HEAL_DEPTH = 3


class VerifyStatus(str, Enum):
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"
    ESCALATED = "escalated"


def verify_finding(
    finding: HealingFinding,
    detect_fn: Callable[..., list[HealingFinding]],
    detect_kwargs: dict,
    heal_depth: int = 1,
) -> VerifyStatus:
    """Re-run detector and check if the finding is resolved.

    Args:
        finding: The original finding to verify.
        detect_fn: The detector function to re-run.
        detect_kwargs: Kwargs to pass to the detector.
        heal_depth: Current remediation attempt count.

    Returns:
        VERIFIED if the finding no longer appears.
        ESCALATED if heal_depth >= MAX_HEAL_DEPTH.
        UNRESOLVED otherwise.
    """
    if heal_depth >= MAX_HEAL_DEPTH:
        return VerifyStatus.ESCALATED

    new_findings = detect_fn(**detect_kwargs)
    # Check if the specific entity is still in the findings
    still_present = any(
        f.entity == finding.entity and f.issue_type == finding.issue_type
        for f in new_findings
    )

    if not still_present:
        return VerifyStatus.VERIFIED
    return VerifyStatus.UNRESOLVED
