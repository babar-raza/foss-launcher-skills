"""Compliance tracking: monitor violations and calculate scores.

This module provides compliance tracking for Kilo Code to monitor
violations and calculate compliance scores.

Usage:
    # Import and use in other scripts
    from kilocode_compliance import ComplianceTracker

    tracker = ComplianceTracker()
    tracker.record_violation("page-plan", "Skill bypass detected", "HIGH")
    print(tracker.generate_feedback())
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent  # scripts/pipeline/lib/ -> pipeline/ -> scripts/ -> repo root


class ComplianceTracker:
    """Track compliance violations and generate feedback.

    This class monitors Kilo Code's adherence to repository rules
    and calculates compliance scores based on violations.
    """

    SEVERITY_WEIGHTS: Dict[str, int] = {
        "CRITICAL": 25,
        "HIGH": 15,
        "MEDIUM": 10,
        "LOW": 5
    }

    def __init__(self, violations_file: Path | None = None):
        """Initialize the compliance tracker.

        Args:
            violations_file: Path to store violations. Defaults to reports/kilocode_violations.json
        """
        self.violations: List[Dict] = []
        self.score_history: List[Tuple[str, float]] = []

        if violations_file is None:
            self.violations_file = _REPO_ROOT / "reports" / "kilocode" / "violations.json"
        else:
            self.violations_file = violations_file

        self._load_violations()

    def _load_violations(self) -> None:
        """Load violations from file if it exists."""
        if self.violations_file.exists():
            try:
                with open(self.violations_file, encoding="utf-8") as f:
                    self.violations = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.violations = []

    def _save_violations(self) -> None:
        """Save violations to file."""
        self.violations_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.violations_file, "w", encoding="utf-8") as f:
            json.dump(self.violations, f, indent=2)

    def record_violation(self, skill: str, violation: str, severity: str) -> None:
        """Record a compliance violation.

        Args:
            skill: Name of the skill where violation occurred
            violation: Description of the violation
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)
        """
        self.violations.append({
            "skill": skill,
            "violation": violation,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
            "severity_weight": self.SEVERITY_WEIGHTS.get(severity, 10)
        })
        self._save_violations()

    def calculate_compliance_score(self) -> float:
        """Calculate compliance score (0-100).

        Returns:
            Compliance score where 100 is perfect and 0 is worst
        """
        if not self.violations:
            return 100.0

        total_weight = sum(v["severity_weight"] for v in self.violations)
        return max(0.0, 100.0 - total_weight)

    def get_violation_summary(self) -> Dict[str, int]:
        """Get a summary of violations by severity.

        Returns:
            Dict mapping severity levels to counts
        """
        summary: Dict[str, int] = {}
        for v in self.violations:
            severity = v["severity"]
            summary[severity] = summary.get(severity, 0) + 1
        return summary

    def generate_feedback(self) -> str:
        """Generate compliance feedback for the agent.

        Returns:
            Formatted feedback string
        """
        if not self.violations:
            return "No compliance violations detected."

        summary = self.get_violation_summary()
        summary_str = ", ".join(f"{k}: {v}" for k, v in summary.items())

        return f"""
Compliance Score: {self.calculate_compliance_score():.1f}%
Violations: {len(self.violations)} ({summary_str})

Recent violations:
{chr(10).join(f"- {v['skill']}: {v['violation']} ({v['severity']})" for v in self.violations[-5:])}
"""

    def clear_violations(self) -> None:
        """Clear all recorded violations."""
        self.violations = []
        self._save_violations()


def get_compliance_tracker() -> ComplianceTracker:
    """Get a global compliance tracker instance.

    Returns:
        ComplianceTracker instance
    """
    return ComplianceTracker()


# Global instance for convenience
_tracker: ComplianceTracker | None = None


def tracker() -> ComplianceTracker:
    """Get or create the global compliance tracker.

    Returns:
        ComplianceTracker instance
    """
    global _tracker
    if _tracker is None:
        _tracker = ComplianceTracker()
    return _tracker
