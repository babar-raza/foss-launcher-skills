"""publish_classifier.py — S-90 Publish Review Auto-Classification Engine.

Deterministic page classification for S-90 publish readiness review.
Replaces manual Steps 5c/5d/5f/7 (classification + routing).

Classifications:
    PUBLISH_READY       — Grade A/B + 0 FAIL findings → auto-publishable
    ACCEPTABLE_GRADE_C  — Grade C reference + evidence.apis non-empty → acceptable
    NEEDS_ACTION_S21    — Grade C non-reference → route to S-21 (page-enhance)
    NEEDS_ACTION_S26    — Grade D → route to S-26 (grade-remediate)
    BLOCKED             — Grade F → blocked, requires investigation

TC-S90-001: Automates S-90 inspection classification (2-4 hours → seconds).
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Classification results
# ---------------------------------------------------------------------------

CLASSIFICATION_LABELS = (
    "PUBLISH_READY",
    "ACCEPTABLE_GRADE_C",
    "NEEDS_ACTION_S21",
    "NEEDS_ACTION_S26",
    "BLOCKED",
)


@dataclass
class ClassificationResult:
    filepath: str
    grade: str
    classification: str
    fail_count: int = 0
    has_apis: bool = False
    is_reference: bool = False
    suggested_skill: str = ""


@dataclass
class ProductClassification:
    family: str
    platform: str
    total_pages: int = 0
    results: list[ClassificationResult] = field(default_factory=list)
    spot_check_sample: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {label: 0 for label in CLASSIFICATION_LABELS}
        for r in self.results:
            counts[r.classification] = counts.get(r.classification, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def classify_page(
    grade: str,
    fail_count: int,
    is_reference: bool,
    has_apis: bool,
) -> tuple[str, str]:
    """Classify a single page based on eval signals.

    Returns (classification, suggested_skill).
    """
    grade_upper = grade.upper() if grade else ""

    if grade_upper in ("A", "B") and fail_count == 0:
        return "PUBLISH_READY", ""

    if grade_upper == "C":
        if is_reference and has_apis:
            return "ACCEPTABLE_GRADE_C", ""
        return "NEEDS_ACTION_S21", "S-21"

    if grade_upper == "D":
        return "NEEDS_ACTION_S26", "S-26"

    if grade_upper == "F":
        return "BLOCKED", ""

    # Unknown grade — treat as needs action
    if grade_upper == "C":
        return "NEEDS_ACTION_S21", "S-21"

    return "NEEDS_ACTION_S26", "S-26"


def classify_from_eval_report(
    filepath: str,
    eval_data: dict[str, Any],
) -> ClassificationResult:
    """Classify a page from its evaluation report data.

    Args:
        filepath: Path to the content file.
        eval_data: Dict with keys: grade, findings (list of finding dicts),
                   evidence (dict with apis list).
    """
    grade = eval_data.get("grade", "")
    findings = eval_data.get("findings", [])
    fail_count = sum(1 for f in findings if f.get("level") == "FAIL")
    evidence = eval_data.get("evidence", {})
    apis = evidence.get("apis", []) if isinstance(evidence, dict) else []
    has_apis = bool(apis)
    is_reference = "reference.aspose.org" in filepath

    classification, skill = classify_page(grade, fail_count, is_reference, has_apis)

    return ClassificationResult(
        filepath=filepath,
        grade=grade,
        classification=classification,
        fail_count=fail_count,
        has_apis=has_apis,
        is_reference=is_reference,
        suggested_skill=skill,
    )


def select_spot_check_sample(
    results: list[ClassificationResult],
    sample_pct: float = 0.10,
    seed: int | None = None,
) -> list[str]:
    """Select a reproducible random sample of PUBLISH_READY pages for human spot-check.

    Args:
        results: Full classification results.
        sample_pct: Fraction to sample (default 10%).
        seed: Random seed for reproducibility. If None, uses a hash of filepaths.
    """
    publish_ready = [r.filepath for r in results if r.classification == "PUBLISH_READY"]
    if not publish_ready:
        return []

    sample_size = max(1, int(len(publish_ready) * sample_pct))

    if seed is None:
        # Deterministic seed from sorted filepaths
        h = hashlib.md5("".join(sorted(publish_ready)).encode()).hexdigest()
        seed = int(h[:8], 16)

    rng = random.Random(seed)
    return sorted(rng.sample(publish_ready, min(sample_size, len(publish_ready))))


def classify_product(
    family: str,
    platform: str,
    page_evals: dict[str, dict[str, Any]],
    spot_check_pct: float = 0.10,
    spot_check_seed: int | None = None,
) -> ProductClassification:
    """Classify all pages for a product.

    Args:
        family: Product family.
        platform: Platform.
        page_evals: Dict mapping filepath → eval_data dict.
        spot_check_pct: Fraction of PUBLISH_READY pages to sample.
        spot_check_seed: Seed for reproducible sampling.
    """
    results = [
        classify_from_eval_report(fp, data)
        for fp, data in sorted(page_evals.items())
    ]

    sample = select_spot_check_sample(results, spot_check_pct, spot_check_seed)

    return ProductClassification(
        family=family,
        platform=platform,
        total_pages=len(results),
        results=results,
        spot_check_sample=sample,
    )


def to_json_report(pc: ProductClassification) -> dict:
    """Convert a ProductClassification to a JSON-serializable report."""
    return {
        "family": pc.family,
        "platform": pc.platform,
        "total_pages": pc.total_pages,
        "summary": pc.summary,
        "spot_check_sample": pc.spot_check_sample,
        "pages": [
            {
                "filepath": r.filepath,
                "grade": r.grade,
                "classification": r.classification,
                "fail_count": r.fail_count,
                "has_apis": r.has_apis,
                "is_reference": r.is_reference,
                "suggested_skill": r.suggested_skill,
            }
            for r in pc.results
        ],
    }
