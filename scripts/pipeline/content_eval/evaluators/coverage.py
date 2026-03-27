"""Coverage evaluator — detects important missing API capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")


def _compute_class_importance(entry: dict) -> float:
    """Score 0.0-1.0 based on method count, properties, tests, docs."""
    mc = entry.get("method_count", 0)
    pc = entry.get("property_count", 0)
    base = min(1.0, (mc + pc) / 20)
    if entry.get("has_tests"):
        base += 0.15
    if entry.get("has_doc"):
        base += 0.1
    # Penalize likely internal classes (only __init__)
    if mc <= 1 and pc == 0:
        base -= 0.2
    return max(0.0, min(1.0, base))


class CoverageEvaluator(BaseEvaluator):
    """Detects important API capabilities missing from content.

    Compares classes and key methods mentioned in content against the
    knowledge model to identify coverage gaps, weighted by class importance.
    """

    name = "coverage"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        # Only check docs and reference pages for coverage
        if page.page_role not in ("docs", "reference"):
            return []

        # Load index.json for class list
        index_path = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "index.json"
        if not index_path.exists():
            return []

        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return []

        all_classes = set(index.get("classes", []))
        if not all_classes:
            return []

        # Load coverage_matrix.json for importance scoring
        matrix_path = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "coverage_matrix.json"
        class_importance: dict[str, float] = {}
        if matrix_path.exists():
            try:
                matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                for entry in matrix:
                    cname = entry.get("class", "")
                    if cname:
                        class_importance[cname] = _compute_class_importance(entry)
            except (json.JSONDecodeError, KeyError):
                pass

        # Extract classes mentioned in page (from code blocks and prose)
        mentioned_classes: set[str] = set()
        for block in page.code_blocks:
            for word in set(re.findall(r"\b([A-Z][A-Za-z0-9]+)\b", block.content)):
                mentioned_classes.add(word)
        for _, line in page.prose_lines:
            for word in set(re.findall(r"`([A-Z][A-Za-z0-9]+)`", line)):
                mentioned_classes.add(word)

        findings: list[Finding] = []

        # Find important classes that are missing from this page
        missing = all_classes - mentioned_classes
        important_missing = [
            (cls, class_importance.get(cls, 0.0))
            for cls in missing
            if class_importance.get(cls, 0.0) >= 0.4
        ]
        important_missing.sort(key=lambda x: x[1], reverse=True)

        if important_missing and len(important_missing) >= 3:
            top5 = important_missing[:5]
            names = ", ".join(f"`{c}`" for c, _ in top5)
            findings.append(Finding(
                level="INFO",
                category="CG",
                filepath=str(page.filepath),
                line_no=1,
                message=f"{len(important_missing)} important classes not documented; top: {names}",
                suggestion="Consider documenting these high-value API classes",
                evaluator=self.name,
            ))

        # Also keep the global coverage check for very low coverage
        if mentioned_classes:
            coverage_pct = len(mentioned_classes & all_classes) / max(len(all_classes), 1) * 100
            if page.page_role == "docs" and coverage_pct < 5 and len(all_classes) > 10:
                findings.append(Finding(
                    level="INFO",
                    category="CG",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Low API coverage: {coverage_pct:.0f}% of {len(all_classes)} known classes mentioned",
                    suggestion="Consider documenting more classes from the API surface",
                    evaluator=self.name,
                ))

        return findings
