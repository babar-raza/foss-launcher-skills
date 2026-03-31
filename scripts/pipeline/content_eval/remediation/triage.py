"""Triage engine — classifies eval findings into fix buckets.

Each finding is classified as:
  auto   — deterministic fixer available
  llm    — needs LLM-assisted rewrite (grounded in knowledge)
  human  — needs human review
  skip   — INFO-level or not worth fixing
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import Finding


@dataclass(slots=True)
class TriagedFinding:
    """A finding with its triage classification."""

    finding: Finding
    fix_type: str       # auto, llm, human, skip
    fixer_name: str     # name of the fixer (empty for llm/human/skip)
    reason: str         # why this classification


@dataclass
class TriageResult:
    """Aggregated triage output."""

    total: int = 0
    auto_fixable: list[TriagedFinding] = field(default_factory=list)
    llm_needed: list[TriagedFinding] = field(default_factory=list)
    human_needed: list[TriagedFinding] = field(default_factory=list)
    skipped: list[TriagedFinding] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "total": self.total,
            "auto_fixable": len(self.auto_fixable),
            "llm_needed": len(self.llm_needed),
            "human_needed": len(self.human_needed),
            "skipped": len(self.skipped),
        }


# -----------------------------------------------------------------------
# Triage rules — ordered list, first match wins
# (category, level_set, message_regex, fix_type, fixer_name, reason)
# -----------------------------------------------------------------------
_TRIAGE_RULES: list[tuple[str, set[str], str, str, str, str]] = [
    # --- Auto-fixable (frontmatter) ---
    ("RV", {"FAIL", "WARN"}, r"(?i)type[:\s]", "auto", "frontmatter_type",
     "Missing frontmatter type field"),
    ("RV", {"FAIL", "WARN"}, r"(?i)author", "auto", "frontmatter_author",
     "Missing frontmatter author field"),
    ("RV", {"WARN"}, r"(?i)categories", "auto", "frontmatter_categories",
     "Missing frontmatter categories field"),
    ("RV", {"WARN"}, r"(?i)layout.*reference", "auto", "frontmatter_layout",
     "Missing layout: reference-single field"),

    # --- Auto-fixable (body structure) ---
    ("RV", {"WARN"}, r"(?i)steps.*shortcode", "auto", "steps_shortcode",
     "Missing {{% steps %}} shortcode wrapper"),
    ("ST", {"FAIL", "WARN"}, r"(?i)placeholder|todo|tbd|fixme", "auto", "placeholder_remove",
     "Placeholder text detected"),
    ("ST", {"WARN", "FAIL"}, r"(?i)(?:missing|no)\s+language", "auto", "code_fence_lang",
     "Code fence missing language tag"),
    ("EG", {"FAIL", "WARN", "INFO"}, r"(?i)evidence", "auto", "evidence_attach",
     "Missing or incomplete evidence block"),

    # --- LLM-needed (structural, needs knowledge context) ---
    ("ST", {"WARN"}, r"(?i)missing.*description", "llm", "",
     "Missing description requires knowledge-grounded generation"),
    ("RV", {"WARN"}, r"(?i)FAQ has only.*question", "llm", "",
     "Too few FAQ questions — generate from claims.json"),
    ("RV", {"WARN"}, r"(?i)no markdown table", "llm", "",
     "Reference page missing API table — generate from api_surface.json"),

    # --- LLM-needed (content quality) ---
    ("RL", {"FAIL", "WARN"}, r".*", "llm", "",
     "Risk language requires context-aware rewrite"),
    ("AA", {"FAIL", "WARN"}, r".*", "llm", "",
     "API accuracy issue requires knowledge-grounded fix"),
    ("PC", {"FAIL", "WARN"}, r".*", "llm", "",
     "Platform contamination requires code replacement"),
    ("FC", {"FAIL"}, r".*", "llm", "",
     "Forbidden claim requires removal and rewrite"),
    ("PT", {"FAIL", "WARN"}, r".*", "llm", "",
     "Prose truth issue requires knowledge-grounded correction"),
    ("CP", {"FAIL", "WARN"}, r".*", "llm", "",
     "Code plausibility issue requires snippet replacement"),
]

# Category-to-evaluator mapping (used by category-fix command)
CATEGORY_TO_EVALUATOR: dict[str, str] = {
    "AA": "api_accuracy",
    "PC": "platform_purity",
    "FC": "forbidden_claims",
    "RV": "page_role",
    "ST": "structure",
    "RL": "risk_language",
    "EG": "evidence_depth",
    "PT": "prose_truth",
    "CP": "code_plausibility",
    "CG": "coverage",
}


def triage_finding(finding: Finding) -> TriagedFinding:
    """Classify a single finding. First matching rule wins."""
    for cat, levels, msg_re, fix_type, fixer, reason in _TRIAGE_RULES:
        if finding.category != cat:
            continue
        if finding.level not in levels:
            continue
        if not re.search(msg_re, finding.message):
            continue
        return TriagedFinding(
            finding=finding,
            fix_type=fix_type,
            fixer_name=fixer,
            reason=reason,
        )

    # Default fallback
    if finding.level in ("FAIL", "WARN"):
        return TriagedFinding(
            finding=finding,
            fix_type="human",
            fixer_name="",
            reason=f"No auto-fixer for {finding.category}/{finding.level}",
        )
    return TriagedFinding(
        finding=finding,
        fix_type="skip",
        fixer_name="",
        reason="INFO-level finding, no action needed",
    )


def triage_findings(findings: list[Finding]) -> TriageResult:
    """Classify all findings into triage buckets."""
    result = TriageResult(total=len(findings))

    for f in findings:
        tf = triage_finding(f)
        if tf.fix_type == "auto":
            result.auto_fixable.append(tf)
        elif tf.fix_type == "llm":
            result.llm_needed.append(tf)
        elif tf.fix_type == "human":
            result.human_needed.append(tf)
        else:
            result.skipped.append(tf)

    return result
