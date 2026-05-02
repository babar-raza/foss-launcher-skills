"""
TC-S96-009: Editorial Review Classifier.

Applies page-type-aware editorial rules to classify each changed file
as GOOD_KEEP, BAD_REVERT, RISKY_REVIEW, or UNCLEAR_NEEDS_EVIDENCE.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_RULES_PATH = _REPO_ROOT / "scripts" / "pipeline" / "config" / "cleanroom_page_rules.yaml"

_GRADE_ORDER = ["A", "B", "C", "D", "F"]


class Verdict(str, Enum):
    GOOD_KEEP = "GOOD_KEEP"
    BAD_REVERT = "BAD_REVERT"
    RISKY_REVIEW = "RISKY_REVIEW"
    UNCLEAR_NEEDS_EVIDENCE = "UNCLEAR_NEEDS_EVIDENCE"


@dataclass
class ClassifyResult:
    path: str
    verdict: Verdict
    reason: str
    profile_used: str
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)


def load_rules(rules_path: Optional[pathlib.Path] = None) -> dict:
    """Load cleanroom_page_rules.yaml. Returns the parsed dict."""
    p = rules_path or _RULES_PATH
    if not p.exists():
        return {"profiles": {}, "grade_order": _GRADE_ORDER, "subdomain_defaults": {}}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _parse_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(content[3:end].strip())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _detect_subdomain(path: str) -> str:
    p = path.replace("\\", "/")
    if "reference.aspose.org" in p:
        return "reference"
    if "blog.aspose.org" in p:
        return "blog"
    if "docs.aspose.org" in p:
        return "docs"
    if "kb.aspose.org" in p:
        return "kb"
    if "products.aspose.org" in p:
        return "products"
    return "unknown"


def select_profile(path: str, fm: dict, rules: dict) -> Tuple[str, dict]:
    """Select the best matching page profile. Returns (name, profile_dict)."""
    profiles = rules.get("profiles", {})
    filename = pathlib.Path(path).name
    subdomain = _detect_subdomain(path)

    # Priority 1: match by subdomain + layout/type (most specific)
    layout = fm.get("layout", "")
    page_type = fm.get("type", "")

    for name, profile in profiles.items():
        match = profile.get("match", {})
        # Skip filename-only profiles in this pass
        if match.get("filename") and not match.get("subdomain") and not match.get("layout") and not match.get("type"):
            continue
        if match.get("subdomain") and match["subdomain"] != subdomain:
            continue
        if match.get("layout") and match["layout"] != layout:
            continue
        if match.get("type") and match["type"] != page_type:
            continue
        if match.get("filename") and match["filename"] != filename:
            continue
        return name, profile

    # Priority 2: filename-only fallback (e.g., section_index by _index.md)
    for name, profile in profiles.items():
        match = profile.get("match", {})
        if match.get("filename") and match["filename"] == filename:
            return name, profile

    # Priority 3: subdomain default
    defaults = rules.get("subdomain_defaults", {})
    if subdomain in defaults:
        profile_name = defaults[subdomain]
        if profile_name in profiles:
            return profile_name, profiles[profile_name]

    return "unknown", {}


def _grade_regression(baseline_grade: str, current_grade: str, allowed: Optional[int]) -> bool:
    """Return True if grade regression exceeds allowed levels."""
    if allowed is None:
        return False
    grade_order = _GRADE_ORDER
    if baseline_grade not in grade_order or current_grade not in grade_order:
        return False
    base_idx = grade_order.index(baseline_grade)
    curr_idx = grade_order.index(current_grade)
    regression = curr_idx - base_idx  # positive = regression
    return regression > abs(allowed) if allowed is not None else False


def classify_file(
    path: str,
    content: str,
    diff_entry: Any,
    baseline_fm: Dict[str, Any],
    rules: dict,
) -> ClassifyResult:
    """Classify a single file change as GOOD_KEEP / BAD_REVERT / RISKY_REVIEW / UNCLEAR."""
    fm = _parse_frontmatter(content)
    profile_name, profile = select_profile(path, fm, rules)

    checks_passed: List[str] = []
    bad_reasons: List[str] = []
    risky_reasons: List[str] = []
    unclear_reasons: List[str] = []

    filename = pathlib.Path(path).name
    subdomain = _detect_subdomain(path)

    # 1. Leading-hyphen filename
    stem = pathlib.Path(path).stem
    if stem.startswith("-"):
        bad_reasons.append("Leading-hyphen filename")

    # 2. Protected page (auto_updatable: false in baseline)
    if baseline_fm.get("auto_updatable") is False:
        bad_reasons.append("Protected page (auto_updatable: false) was modified")

    # 3. Churn-only edit
    churn_signals = getattr(diff_entry, "churn_signals", []) if diff_entry else []
    if churn_signals and _is_churn_only(churn_signals):
        bad_reasons.append(f"Churn-only change: {', '.join(churn_signals)}")

    # 4. Required frontmatter fields
    required = profile.get("required_frontmatter", [])
    for req_field in required:
        if req_field not in fm:
            bad_reasons.append(f"Missing required frontmatter field: {req_field}")
        else:
            checks_passed.append(f"required:{req_field}")

    # 5. Blog-specific checks
    if profile.get("author_must_be_aspose"):
        author = fm.get("author", "")
        if author != "Aspose":
            bad_reasons.append(f"Blog author must be 'Aspose', got: {author!r}")
        else:
            checks_passed.append("author:Aspose")

    if profile.get("path_must_be_directory"):
        p_norm = path.replace("\\", "/")
        if not p_norm.endswith("/index.md"):
            bad_reasons.append("Blog post must use {slug}/index.md directory pattern, not flat file")

    # 6. Evidence block check (products pages)
    if profile.get("evidence_block_forbidden"):
        if "evidence" in fm:
            risky_reasons.append("Evidence block found on products page (structural violation)")

    # 7. Grade regression
    if baseline_fm.get("grade") and fm.get("grade"):
        allowed = profile.get("grade_movement_allowed")
        if allowed is not None and _grade_regression(baseline_fm["grade"], fm["grade"], allowed):
            # Severe regression (more than 1 level) → BAD_REVERT
            base_idx = _GRADE_ORDER.index(baseline_fm["grade"]) if baseline_fm["grade"] in _GRADE_ORDER else -1
            curr_idx = _GRADE_ORDER.index(fm["grade"]) if fm["grade"] in _GRADE_ORDER else -1
            regression = curr_idx - base_idx
            if regression >= 2:  # B→D or worse
                bad_reasons.append(
                    f"Grade regressed severely: {baseline_fm['grade']} → {fm['grade']}"
                )
            else:
                risky_reasons.append(
                    f"Grade regressed: {baseline_fm['grade']} → {fm['grade']}"
                )

    # 8. Unclosed shortcode
    if profile.get("shortcode_check"):
        if re.search(r"\{\{<[^>]*$", content, re.MULTILINE):
            bad_reasons.append("Unclosed Hugo shortcode detected")

    # 9. Slug mismatch
    fm_slug = fm.get("slug")
    if fm_slug and filename != "_index.md":
        file_stem = pathlib.Path(path).stem
        slug_norm = fm_slug.strip().lower().replace(" ", "-")
        if slug_norm != file_stem.lower() and slug_norm != file_stem:
            risky_reasons.append(
                f"Slug mismatch: frontmatter slug={fm_slug!r}, file stem={file_stem!r}"
            )

    # Apply verdict hierarchy
    if bad_reasons:
        return ClassifyResult(
            path=path,
            verdict=Verdict.BAD_REVERT,
            reason="; ".join(bad_reasons),
            profile_used=profile_name,
            checks_passed=checks_passed,
            checks_failed=bad_reasons + risky_reasons,
        )
    if risky_reasons:
        return ClassifyResult(
            path=path,
            verdict=Verdict.RISKY_REVIEW,
            reason="; ".join(risky_reasons),
            profile_used=profile_name,
            checks_passed=checks_passed,
            checks_failed=risky_reasons,
        )
    if unclear_reasons:
        return ClassifyResult(
            path=path,
            verdict=Verdict.UNCLEAR_NEEDS_EVIDENCE,
            reason="; ".join(unclear_reasons),
            profile_used=profile_name,
            checks_passed=checks_passed,
            checks_failed=unclear_reasons,
        )

    return ClassifyResult(
        path=path,
        verdict=Verdict.GOOD_KEEP,
        reason="All checks passed",
        profile_used=profile_name,
        checks_passed=checks_passed,
        checks_failed=[],
    )


def _is_churn_only(signals: List[str]) -> bool:
    churn = {"timestamp_only", "whitespace_only", "yaml_reorder",
             "line_wrap_only", "shortcode_format", "grade_churn"}
    return bool(signals) and all(s in churn for s in signals)
