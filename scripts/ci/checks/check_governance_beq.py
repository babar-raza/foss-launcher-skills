# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
"""Behavioral Equivalence (BEQ) check for governance refactor routing.

Verifies that each AGENTS.md stub section correctly routes to its child
document and that the child document contains substantive content.

BEQ paths checked:
  BEQ-01: §3  → docs/workflows/mental-model-refresh.md
  BEQ-02: §4  → docs/governance/write-boundaries.md
  BEQ-03: §4b → docs/governance/python-placement.md
  BEQ-04: §6  → docs/workflows/skill-chains.md
  BEQ-05: §6a → docs/governance/dar-table.md
  BEQ-06: §6b → docs/workflows/gap-escalation.md
  BEQ-07: §9  → docs/workflows/maintenance.md
  BEQ-08: §10 → docs/governance/evidence-and-provenance.md
  BEQ-09: §14 → docs/workflows/completion-verification.md
  BEQ-10: §12 → docs/registries/skills.md + docs/registries/file-map.md

Usage:
    python scripts/ci/checks/check_governance_beq.py
    python scripts/ci/checks/check_governance_beq.py --json

Exit codes:
    0  All BEQ paths verified
    1  One or more BEQ paths broken
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[3])))
AGENTS_MD = REPO_ROOT / "AGENTS.md"

# BEQ routing table: (beq_id, section_label, child_doc_path, min_lines)
# min_lines = minimum substantive content lines expected in child doc
BEQ_ROUTES: list[tuple[str, str, str, int]] = [
    ("BEQ-01", "§3",  "docs/workflows/mental-model-refresh.md", 10),
    ("BEQ-02", "§4",  "docs/governance/write-boundaries.md", 10),
    ("BEQ-03", "§4b", "docs/governance/python-placement.md", 5),
    ("BEQ-04", "§6",  "docs/workflows/skill-chains.md", 10),
    ("BEQ-05", "§6a", "docs/governance/dar-table.md", 10),
    ("BEQ-06", "§6b", "docs/workflows/gap-escalation.md", 10),
    ("BEQ-07", "§9",  "docs/workflows/maintenance.md", 5),
    ("BEQ-08", "§10", "docs/governance/evidence-and-provenance.md", 10),
    ("BEQ-09", "§14", "docs/workflows/completion-verification.md", 5),
    ("BEQ-10a", "§12", "docs/registries/skills.md", 20),
    ("BEQ-10b", "§12", "docs/registries/file-map.md", 20),
]


def check_routes(as_json: bool = False) -> int:
    """Run all BEQ checks. Returns exit code."""
    agents_text = AGENTS_MD.read_text(encoding="utf-8")
    issues: list[dict] = []
    passed: list[str] = []

    for beq_id, section, child_path, min_lines in BEQ_ROUTES:
        child_full = REPO_ROOT / child_path

        # Check 1: AGENTS.md contains a pointer to the child doc
        if child_path not in agents_text:
            issues.append({
                "beq": beq_id,
                "check": "missing_pointer",
                "detail": f"{beq_id}: AGENTS.md {section} does not reference {child_path}",
            })
            continue

        # Check 2: Child doc exists
        if not child_full.exists():
            issues.append({
                "beq": beq_id,
                "check": "missing_child_doc",
                "detail": f"{beq_id}: {child_path} does not exist",
            })
            continue

        # Check 3: Child doc has substantive content
        child_text = child_full.read_text(encoding="utf-8")
        line_count = len(child_text.splitlines())
        if line_count < min_lines:
            issues.append({
                "beq": beq_id,
                "check": "insufficient_content",
                "detail": f"{beq_id}: {child_path} has {line_count} lines (minimum: {min_lines})",
            })
            continue

        passed.append(beq_id)

    if as_json:
        result = {
            "passed": passed,
            "passed_count": len(passed),
            "issue_count": len(issues),
            "issues": issues,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"BEQ checks: {len(passed)} passed, {len(issues)} failed")
        if passed:
            print(f"  PASS: {', '.join(passed)}")
        if issues:
            print()
            for issue in issues:
                print(f"  FAIL: {issue['detail']}")
            print(f"\nFAIL: {len(issues)} BEQ routing path(s) broken")
        else:
            print("\nPASS: all governance routing paths verified")

    return 1 if issues else 0


def main() -> int:
    as_json = "--json" in sys.argv
    return check_routes(as_json=as_json)


if __name__ == "__main__":
    raise SystemExit(main())
