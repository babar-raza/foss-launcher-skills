"""Agent Decision Board — deterministic review layer replacing human review.

Evaluates shadow candidates using quality scoring and claim verification
to produce APPROVED_FOR_DRAFT_WRITE, REPAIR_REQUIRED, or QUARANTINED
decisions without human intervention.

Routine decisions (delegable):
    - Structural quality pass/fail
    - Claim verification pass/fail
    - Section completeness
    - Metadata validation
    - Word count thresholds

Non-delegable (always requires human):
    - New product family launch (first-ever content)
    - Quality regression > 20% from baseline
    - Quarantine release
    - Schema version changes

Public API:
    BoardDecision       — per-candidate decision record
    BoardVerdict        — aggregate verdict for a product
    DecisionType        — enum of decision outcomes
    review_candidate    — review one candidate
    review_candidates   — review a batch of candidates
    is_delegable        — check if a decision can be made without human
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lib.content_quality import (
    CandidateScore,
    score_candidate,
    score_candidates_dir,
)
from lib.schema_validators import (
    validate_shadow_candidate,
    validate_candidate_sections,
)

BOARD_SCHEMA_VERSION = "1.0.0"

# Thresholds
MIN_GATE_PASS_RATIO = 0.8  # At least 80% of gates must pass for REPAIR
QUARANTINE_GATE_PASS_RATIO = 0.5  # Below 50% → quarantine


class DecisionType(str, Enum):
    """Possible agent board decisions."""
    APPROVED = "approved_for_draft_write"
    REPAIR_REQUIRED = "repair_required"
    QUARANTINED = "quarantined"
    NON_DELEGABLE = "non_delegable_human_required"


@dataclass
class BoardDecision:
    """Decision record for a single candidate."""
    candidate_path: str
    decision: str  # DecisionType value
    gate_pass_ratio: float
    failed_gates: list[str] = field(default_factory=list)
    structural_errors: list[str] = field(default_factory=list)
    section_errors: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BoardVerdict:
    """Aggregate verdict for a product review."""
    schema_version: str = BOARD_SCHEMA_VERSION
    family: str = ""
    platform: str = ""
    total_candidates: int = 0
    approved: int = 0
    repair_required: int = 0
    quarantined: int = 0
    non_delegable: int = 0
    decisions: list[BoardDecision] = field(default_factory=list)
    is_first_launch: bool = False
    verdict: str = ""  # overall verdict

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decisions"] = [dec.to_dict() for dec in self.decisions]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")


def is_delegable(
    family: str,
    platform: str,
    content_dir: Path | None = None,
    baseline_scores: dict | None = None,
    current_scores: list[CandidateScore] | None = None,
) -> tuple[bool, str]:
    """Check if a review decision can be made without human intervention.

    Returns (is_delegable, reason).
    Non-delegable cases:
      1. First-ever launch (no existing content/ for this product)
      2. Quality regression > 20% from baseline
    """
    # Check for first launch
    if content_dir is not None:
        # Look for any existing content for this family/platform
        has_existing = False
        for subdir in ["docs.aspose.org", "blog.aspose.org", "kb.aspose.org",
                        "products.aspose.org", "reference.aspose.org"]:
            check_path = content_dir / subdir
            if not check_path.exists():
                continue
            # products uses /en/{family}/, others use /en/{family}/{platform}/
            if subdir == "products.aspose.org":
                prod_path = check_path / "en" / family
            else:
                prod_path = check_path / "en" / family / platform
            if prod_path.exists() and any(prod_path.rglob("*.md")):
                has_existing = True
                break

        if not has_existing:
            return False, f"first launch for {family}/{platform} — no existing content"

    # Check quality regression
    if baseline_scores and current_scores:
        baseline_pass_rate = baseline_scores.get("pass_rate", 1.0)
        current_pass_count = sum(1 for s in current_scores if s.passed)
        current_pass_rate = current_pass_count / len(current_scores) if current_scores else 0
        if baseline_pass_rate > 0 and current_pass_rate < baseline_pass_rate * 0.8:
            return False, (
                f"quality regression: current {current_pass_rate:.1%} < "
                f"80% of baseline {baseline_pass_rate:.1%}"
            )

    return True, "routine review — all conditions delegable"


def review_candidate(
    content: str,
    candidate_path: str = "",
    page_type: str = "reference",
) -> BoardDecision:
    """Review a single candidate and produce a decision.

    Decision logic:
      - All gates pass + no structural/section errors → APPROVED
      - Gate pass ratio >= 80% → REPAIR_REQUIRED
      - Gate pass ratio < 50% → QUARANTINED
      - Between 50-80% → REPAIR_REQUIRED
    """
    # Score with quality gates
    quality_score = score_candidate(content, candidate_path, page_type)

    # Structural validation
    structural_errors = validate_shadow_candidate(content)

    # Section validation
    section_errors = validate_candidate_sections(content, page_type)

    # Calculate gate pass ratio
    ratio = quality_score.passed_gates / quality_score.total_gates if quality_score.total_gates > 0 else 0

    failed_gate_ids = [g.gate_id for g in quality_score.gates if not g.passed]

    # Decision logic
    if quality_score.passed and not structural_errors and not section_errors:
        decision = DecisionType.APPROVED
        reason = f"all {quality_score.total_gates} gates passed, no structural/section errors"
    elif ratio < QUARANTINE_GATE_PASS_RATIO:
        decision = DecisionType.QUARANTINED
        reason = f"gate pass ratio {ratio:.1%} below quarantine threshold {QUARANTINE_GATE_PASS_RATIO:.0%}"
    else:
        decision = DecisionType.REPAIR_REQUIRED
        reasons = []
        if failed_gate_ids:
            reasons.append(f"failed gates: {', '.join(failed_gate_ids)}")
        if structural_errors:
            reasons.append(f"{len(structural_errors)} structural error(s)")
        if section_errors:
            reasons.append(f"{len(section_errors)} section error(s)")
        reason = "; ".join(reasons)

    return BoardDecision(
        candidate_path=candidate_path,
        decision=decision.value,
        gate_pass_ratio=round(ratio, 3),
        failed_gates=failed_gate_ids,
        structural_errors=structural_errors,
        section_errors=section_errors,
        reason=reason,
    )


def review_candidates(
    candidates_dir: Path,
    family: str,
    platform: str,
    page_type_map: dict[str, str] | None = None,
    content_dir: Path | None = None,
    baseline_scores: dict | None = None,
) -> BoardVerdict:
    """Review all candidates in a directory and produce an aggregate verdict.

    Args:
        candidates_dir: Directory with candidate .md files.
        family: Product family.
        platform: Platform.
        page_type_map: Optional filename -> page_type mapping.
        content_dir: Path to content/ for delegability check.
        baseline_scores: Prior baseline scores for regression check.

    Returns BoardVerdict with per-candidate decisions and overall verdict.
    """
    verdict = BoardVerdict(family=family, platform=platform)

    if not candidates_dir.exists():
        verdict.verdict = "no_candidates"
        return verdict

    md_files = sorted(candidates_dir.glob("*.md"))
    verdict.total_candidates = len(md_files)

    if not md_files:
        verdict.verdict = "no_candidates"
        return verdict

    # Score all candidates first (for delegability check)
    all_scores = score_candidates_dir(candidates_dir, page_type_map)

    # Check delegability
    delegable, delegable_reason = is_delegable(
        family, platform, content_dir, baseline_scores, all_scores,
    )

    if not delegable:
        verdict.is_first_launch = "first launch" in delegable_reason
        # Mark all as non-delegable
        for md_file in md_files:
            verdict.decisions.append(BoardDecision(
                candidate_path=md_file.name,
                decision=DecisionType.NON_DELEGABLE.value,
                gate_pass_ratio=0.0,
                reason=delegable_reason,
            ))
        verdict.non_delegable = len(md_files)
        verdict.verdict = "non_delegable_human_required"
        return verdict

    # Review each candidate
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        pt = "reference"
        if page_type_map:
            pt = page_type_map.get(md_file.name, "reference")
        decision = review_candidate(content, md_file.name, pt)
        verdict.decisions.append(decision)

        if decision.decision == DecisionType.APPROVED.value:
            verdict.approved += 1
        elif decision.decision == DecisionType.REPAIR_REQUIRED.value:
            verdict.repair_required += 1
        elif decision.decision == DecisionType.QUARANTINED.value:
            verdict.quarantined += 1

    # Overall verdict
    if verdict.quarantined > 0:
        verdict.verdict = "quarantined"
    elif verdict.repair_required > 0:
        verdict.verdict = "repair_required"
    elif verdict.approved == verdict.total_candidates:
        verdict.verdict = "approved_for_draft_write"
    else:
        verdict.verdict = "mixed"

    return verdict
