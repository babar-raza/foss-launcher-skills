"""Tests for Tier 3 demotion to advisory (S2-1 fix)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from run import compute_verdict  # type: ignore  # noqa: E402


def test_tier3_m_finding_does_not_block():
    """Tier 3 M-severity finding must NOT produce NOT PUBLISHABLE."""
    findings = [{"severity": "M", "tier_resolved_by": 3, "file": "content/docs/test.md"}]
    assert compute_verdict(findings) == "PUBLICATION READY"


def test_tier1_m_finding_still_blocks():
    """Tier 1 M-severity finding must still produce NOT PUBLISHABLE."""
    findings = [{"severity": "M", "tier_resolved_by": 1, "file": "content/docs/test.md"}]
    assert compute_verdict(findings) == "NOT PUBLISHABLE"


def test_tier2_m_finding_still_blocks():
    """Tier 2 M-severity finding must still produce NOT PUBLISHABLE."""
    findings = [{"severity": "M", "tier_resolved_by": 2, "file": "content/docs/test.md"}]
    assert compute_verdict(findings) == "NOT PUBLISHABLE"


def test_tier3_s_finding_does_not_affect_verdict():
    """Tier 3 S-severity finding must NOT produce CONDITIONAL."""
    findings = [{"severity": "S", "tier_resolved_by": 3, "file": "content/docs/test.md"}]
    assert compute_verdict(findings) == "PUBLICATION READY"


def test_mixed_tier1_and_tier3():
    """Tier 1 S + Tier 3 M -> CONDITIONAL (Tier 3 M ignored, Tier 1 S counts)."""
    findings = [
        {"severity": "S", "tier_resolved_by": 1, "file": "content/docs/test.md"},
        {"severity": "M", "tier_resolved_by": 3, "file": "content/docs/test.md"},
    ]
    assert compute_verdict(findings) == "CONDITIONAL"


def test_suppressed_tier1_still_excluded():
    """Suppressed findings remain excluded regardless of tier."""
    findings = [{"severity": "M", "tier_resolved_by": 1, "file": "content/docs/test.md", "status": "suppressed"}]
    assert compute_verdict(findings) == "PUBLICATION READY"
