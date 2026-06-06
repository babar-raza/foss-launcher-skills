"""Content Quality — deterministic quality scoring for shadow candidates.

Scores candidates against 10 quality gates and produces machine-readable
verdicts. Used by the Agent Decision Board to make approve/repair/quarantine
decisions without human intervention.

Public API:
    CandidateScore  — per-candidate quality result
    QualityGate     — single gate result (pass/fail + reason)
    score_candidate — score one candidate markdown string
    score_candidates_dir — batch-score a directory of candidates
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CONTENT_QUALITY_VERSION = "1.0.0"

MIN_WORD_COUNTS: dict[str, int] = {
    "reference": 30,
    "documentation": 80,
    "product_landing": 60,
    "blog_post": 100,
    "knowledge_base": 60,
}

FORBIDDEN_TERMS: list[str] = [
    "TODO",
    "FIXME",
    "PLACEHOLDER",
    "lorem ipsum",
    "insert here",
    "TBD",
]

REQUIRED_METADATA_KEYS: list[str] = [
    "title",
    "draft",
    "shadow_candidate",
    "generator_version",
    "family",
    "platform",
]


@dataclass
class QualityGate:
    """Result of a single quality gate check."""
    gate_id: str
    passed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateScore:
    """Quality score for a single candidate."""
    candidate_path: str
    page_type: str
    gates: list[QualityGate] = field(default_factory=list)
    passed: bool = True
    total_gates: int = 0
    passed_gates: int = 0
    failed_gates: int = 0
    word_count: int = 0
    fact_ref_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gates"] = [g.to_dict() for g in self.gates]
        return d


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML-like frontmatter from markdown. Returns (metadata, body)."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1]
    body = parts[2]
    metadata: dict[str, str] = {}
    for line in fm_text.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            metadata[key.strip()] = val.strip()
    return metadata, body


def score_candidate(
    content: str,
    candidate_path: str = "",
    page_type: str = "reference",
) -> CandidateScore:
    """Score a candidate markdown string against all quality gates.

    Returns a CandidateScore with gate-by-gate results.
    """
    metadata, body = _parse_frontmatter(content)
    words = body.split()
    word_count = len(words)
    fact_refs = re.findall(r"<!-- fact_ref: (FG-[a-f0-9]+) -->", content)

    score = CandidateScore(
        candidate_path=candidate_path,
        page_type=page_type,
        word_count=word_count,
        fact_ref_count=len(fact_refs),
    )

    gates: list[QualityGate] = []

    # Gate 1: Minimum word count
    min_words = MIN_WORD_COUNTS.get(page_type, 30)
    gates.append(QualityGate(
        gate_id="min_word_count",
        passed=word_count >= min_words,
        reason=f"{word_count} words (min {min_words})" if word_count < min_words else "",
    ))

    # Gate 2: Has sections (at least one ## heading)
    has_sections = "## " in body
    gates.append(QualityGate(
        gate_id="has_sections",
        passed=has_sections,
        reason="no ## headings found" if not has_sections else "",
    ))

    # Gate 3: Has fact references
    gates.append(QualityGate(
        gate_id="has_fact_refs",
        passed=len(fact_refs) > 0,
        reason="no fact_ref markers found" if not fact_refs else "",
    ))

    # Gate 4: Metadata complete
    missing_keys = [k for k in REQUIRED_METADATA_KEYS if k not in metadata]
    gates.append(QualityGate(
        gate_id="metadata_complete",
        passed=len(missing_keys) == 0,
        reason=f"missing: {', '.join(missing_keys)}" if missing_keys else "",
    ))

    # Gate 5: draft: true
    gates.append(QualityGate(
        gate_id="draft_true",
        passed=metadata.get("draft") == "true",
        reason="draft not set to true" if metadata.get("draft") != "true" else "",
    ))

    # Gate 6: shadow_candidate: true
    gates.append(QualityGate(
        gate_id="shadow_marker",
        passed=metadata.get("shadow_candidate") == "true",
        reason="shadow_candidate not set to true" if metadata.get("shadow_candidate") != "true" else "",
    ))

    # Gate 7: Title present and non-empty
    title = metadata.get("title", "").strip().strip('"').strip("'")
    gates.append(QualityGate(
        gate_id="title_present",
        passed=bool(title),
        reason="title is empty or missing" if not title else "",
    ))

    # Gate 8: No forbidden terms
    body_lower = body.lower()
    found_forbidden = [t for t in FORBIDDEN_TERMS if t.lower() in body_lower]
    gates.append(QualityGate(
        gate_id="no_forbidden_terms",
        passed=len(found_forbidden) == 0,
        reason=f"found: {', '.join(found_forbidden)}" if found_forbidden else "",
    ))

    # Gate 9: Has heading (# in body)
    has_heading = bool(re.search(r"^#+ ", body, re.MULTILINE))
    gates.append(QualityGate(
        gate_id="has_heading",
        passed=has_heading,
        reason="no heading found in body" if not has_heading else "",
    ))

    # Gate 10: Family and platform set
    has_family = bool(metadata.get("family", "").strip())
    has_platform = bool(metadata.get("platform", "").strip())
    gates.append(QualityGate(
        gate_id="family_platform_set",
        passed=has_family and has_platform,
        reason="family or platform not set" if not (has_family and has_platform) else "",
    ))

    score.gates = gates
    score.total_gates = len(gates)
    score.passed_gates = sum(1 for g in gates if g.passed)
    score.failed_gates = score.total_gates - score.passed_gates
    score.passed = score.failed_gates == 0

    return score


def score_candidates_dir(
    candidates_dir: Path,
    page_type_map: dict[str, str] | None = None,
) -> list[CandidateScore]:
    """Score all .md files in a directory.

    Args:
        candidates_dir: Directory containing candidate .md files.
        page_type_map: Optional mapping of filename -> page_type.
            If not provided, defaults to "reference" for all.

    Returns list of CandidateScore objects.
    """
    scores: list[CandidateScore] = []
    if not candidates_dir.exists():
        return scores

    for md_file in sorted(candidates_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        pt = "reference"
        if page_type_map:
            pt = page_type_map.get(md_file.name, "reference")
        scores.append(score_candidate(content, str(md_file.name), pt))
    return scores
