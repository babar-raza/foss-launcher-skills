"""candidate_generator.py — Enrichment candidate generation and classification (S-98).

Generates enrichment candidates from coverage gaps, classifies them,
applies scoring, and enforces the denominator invariant.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .taxonomy import (
    CandidateAction,
    CandidateDisposition,
    CoverageStatus,
    ACTION_TO_DISPOSITION,
    SUBDOMAINS,
)
from .feature_detector import generate_feature_candidates

# ---------------------------------------------------------------------------
# Scoring configuration (DRAFT — configurable, not hardcoded)
# ---------------------------------------------------------------------------

DEFAULT_SCORING_CONFIG = {
    "weights": {
        "claim_density": 0.25,
        "api_coverage": 0.20,
        "snippet_availability": 0.20,
        "gap_severity": 0.20,
        "cross_subdomain_synergy": 0.15,
    },
    "thresholds": {
        "generate": 0.70,
        "generate_with_review": 0.50,
        "defer": 0.30,
    },
    "min_claims_for_new_page": 5,
    "min_api_methods_for_new_page": 1,
    "max_new_pages_per_run": 10,
    "blog_quality_gate": True,
}


def load_scoring_config(config_path: Path | None = None) -> dict:
    """Load scoring config from file or return defaults."""
    if config_path and config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return DEFAULT_SCORING_CONFIG.copy()


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def _score_candidate(
    cluster: dict,
    subdomain: str,
    coverage_status: str,
    total_claims: int,
    config: dict,
) -> float:
    """Score a candidate based on configurable weights."""
    weights = config.get("weights", DEFAULT_SCORING_CONFIG["weights"])
    claim_count = cluster.get("claim_count", 0)
    api_count = cluster.get("api_method_count", 0)

    # Claim density: normalized by total claims
    claim_score = min(claim_count / max(total_claims, 1) * 10, 1.0)

    # API coverage: normalized
    api_score = min(api_count / 100, 1.0)

    # Snippet availability: simplified — assume available if claim count > 20
    snippet_score = 1.0 if claim_count > 20 else 0.5

    # Gap severity: uncovered = 1.0, partial = 0.5, product_only = 0.3
    gap_map = {
        "uncovered": 1.0,
        "partially_covered": 0.5,
        "product_mentioned_only": 0.3,
        "reference_only": 0.2,
    }
    gap_score = gap_map.get(coverage_status, 0.0)

    # Cross-subdomain synergy: higher if other subdomains already cover it
    synergy_score = len(cluster.get("sections_present", [])) / 5.0

    total = (
        weights.get("claim_density", 0.25) * claim_score
        + weights.get("api_coverage", 0.20) * api_score
        + weights.get("snippet_availability", 0.20) * snippet_score
        + weights.get("gap_severity", 0.20) * gap_score
        + weights.get("cross_subdomain_synergy", 0.15) * synergy_score
    )
    return round(min(total, 1.0), 3)


def _classify_candidate(
    subdomain: str,
    coverage_status: str,
    score: float,
    cluster: dict,
    config: dict,
) -> CandidateAction:
    """Classify a candidate into an action based on score and context."""
    thresholds = config.get("thresholds", DEFAULT_SCORING_CONFIG["thresholds"])
    min_claims = config.get("min_claims_for_new_page", 5)
    min_api = config.get("min_api_methods_for_new_page", 1)

    claim_count = cluster.get("claim_count", 0)
    api_count = cluster.get("api_method_count", 0)

    # Block if insufficient evidence
    if claim_count < min_claims or api_count < min_api:
        return CandidateAction.REJECT_WITH_REASON

    # Reference subdomain — never generate narrative content for reference
    if subdomain == "reference.aspose.org":
        return CandidateAction.NO_ACTION_REFERENCE_ONLY

    # Products subdomain — product pages are structural, not cluster-driven
    if subdomain == "products.aspose.org":
        return CandidateAction.NO_ACTION_REFERENCE_ONLY

    # Map subdomain to action type
    action_map = {
        "docs.aspose.org": {
            "create": CandidateAction.CREATE_NEW_DOCS_PAGE,
            "update": CandidateAction.UPDATE_EXISTING_DOCS_PAGE,
        },
        "kb.aspose.org": {
            "create": CandidateAction.CREATE_NEW_KB_PAGE,
            "update": CandidateAction.UPDATE_EXISTING_KB_PAGE,
        },
        "blog.aspose.org": {
            "create": CandidateAction.CREATE_NEW_BLOG_POST,
            "update": CandidateAction.UPDATE_EXISTING_BLOG_POST,
        },
    }

    actions = action_map.get(subdomain)
    if not actions:
        return CandidateAction.REJECT_WITH_REASON

    # Determine create vs update
    is_update = coverage_status in ("partially_covered", "product_mentioned_only")
    action_key = "update" if is_update else "create"

    # Apply score thresholds
    if score >= thresholds.get("generate", 0.70):
        return actions[action_key]
    elif score >= thresholds.get("generate_with_review", 0.50):
        # Blog requires stricter quality gate
        if subdomain == "blog.aspose.org" and config.get("blog_quality_gate", True):
            return CandidateAction.DEFER_TO_BACKLOG
        return actions[action_key]
    elif score >= thresholds.get("defer", 0.30):
        return CandidateAction.DEFER_TO_BACKLOG
    else:
        return CandidateAction.REJECT_WITH_REASON


def _build_reason(action: CandidateAction, cluster: dict, subdomain: str, score: float) -> str:
    """Build a human-readable reason for the classification."""
    if action == CandidateAction.REJECT_WITH_REASON:
        if cluster.get("claim_count", 0) < 5:
            return f"Insufficient claims ({cluster.get('claim_count', 0)} < 5)"
        if cluster.get("api_method_count", 0) < 1:
            return f"No API methods for {cluster['category']}"
        return f"Score too low ({score:.3f}) for {subdomain}"
    if action == CandidateAction.NO_ACTION_REFERENCE_ONLY:
        return f"{subdomain} is structural/reference — no narrative enrichment"
    if action == CandidateAction.DEFER_TO_BACKLOG:
        return f"Score {score:.3f} below generate threshold; deferred for future review"
    if action == CandidateAction.BLOCK_WITH_REASON:
        return "System gap prevents generation"
    return ""


def generate_candidates(audit_result: dict, config: dict | None = None) -> dict:
    """Generate enrichment candidates from coverage audit result.

    Returns a dict with candidates list and denominator breakdown.
    """
    if config is None:
        config = load_scoring_config()

    matrix = audit_result.get("matrix", {})
    clusters = audit_result.get("clusters", [])
    total_claims = audit_result.get("total_claims", 0)
    max_pages = config.get("max_new_pages_per_run", 10)

    candidates = []
    generate_count = 0

    for cluster in clusters:
        cat = cluster["category"]
        row = matrix.get(cat, {})
        for subdomain in SUBDOMAINS:
            coverage_status = row.get(subdomain, "unknown")

            # Skip already covered
            if coverage_status in ("covered",):
                continue

            score = _score_candidate(cluster, subdomain, coverage_status, total_claims, config)
            action = _classify_candidate(subdomain, coverage_status, score, cluster, config)
            disposition = ACTION_TO_DISPOSITION[action]

            # Enforce max pages cap
            if disposition == CandidateDisposition.GENERATE_NOW and generate_count >= max_pages:
                action = CandidateAction.DEFER_TO_BACKLOG
                disposition = CandidateDisposition.DEFERRED_TO_BACKLOG

            if disposition == CandidateDisposition.GENERATE_NOW:
                generate_count += 1

            reason = _build_reason(action, cluster, subdomain, score)

            candidates.append({
                "cluster": cat,
                "subdomain": subdomain,
                "coverage_status": coverage_status,
                "score": score,
                "action": action.value,
                "disposition": disposition.value,
                "reason": reason,
                "claim_count": cluster.get("claim_count", 0),
                "api_method_count": cluster.get("api_method_count", 0),
            })

    # Feature-level candidates from shallow coverage (TC-003)
    shallow_coverage = audit_result.get("shallow_coverage", {})
    feature_groups = audit_result.get("feature_groups", [])
    for cluster in clusters:
        cat = cluster["category"]
        cluster_shallow = shallow_coverage.get(cat, {})
        if not cluster_shallow:
            continue
        row = matrix.get(cat, {})
        feat_candidates = generate_feature_candidates(
            cluster, feature_groups, cluster_shallow, row,
        )
        for fc in feat_candidates:
            subdomain = fc["subdomain"]
            feature_name = fc["feature_group"]

            # Score using "uncovered" gap severity — the feature itself has
            # zero dedicated content even though the parent cluster is "covered"
            feature_score = _score_candidate(
                cluster, subdomain, "uncovered", total_claims, config,
            )
            # Boost score slightly for high-value features
            feature_score = min(round(feature_score + 0.05, 3), 1.0)

            action = _classify_candidate(
                subdomain, "partially_covered", feature_score, cluster, config,
            )
            disposition = ACTION_TO_DISPOSITION[action]

            # Enforce max pages cap
            if disposition == CandidateDisposition.GENERATE_NOW and generate_count >= max_pages:
                action = CandidateAction.DEFER_TO_BACKLOG
                disposition = CandidateDisposition.DEFERRED_TO_BACKLOG

            if disposition == CandidateDisposition.GENERATE_NOW:
                generate_count += 1

            reason = _build_reason(action, cluster, subdomain, feature_score)

            candidates.append({
                "cluster": cat,
                "feature_group": feature_name,
                "subdomain": subdomain,
                "coverage_status": "shallow_covered",
                "score": feature_score,
                "action": action.value,
                "disposition": disposition.value,
                "reason": reason,
                "claim_count": cluster.get("claim_count", 0),
                "api_method_count": cluster.get("api_method_count", 0),
                "coverage_depth": fc.get("coverage_depth", 0),
            })

    # Build denominator breakdown
    denom = {d.value: 0 for d in CandidateDisposition}
    for c in candidates:
        denom[c["disposition"]] += 1

    return {
        "family": audit_result.get("family", ""),
        "platform": audit_result.get("platform", ""),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_candidates": len(candidates),
        "denominator": denom,
        "candidates": candidates,
        "scoring_config": config,
    }


# ---------------------------------------------------------------------------
# Denominator invariant
# ---------------------------------------------------------------------------

def validate_denominator(candidates_result: dict) -> dict:
    """Validate the denominator invariant: total = sum of all disposition buckets."""
    total = candidates_result.get("total_candidates", 0)
    denom = candidates_result.get("denominator", {})
    bucket_sum = sum(denom.values())

    return {
        "valid": total == bucket_sum,
        "total_candidates": total,
        "bucket_sum": bucket_sum,
        "buckets": denom,
        "delta": total - bucket_sum,
    }


# ---------------------------------------------------------------------------
# Decisions and handoff
# ---------------------------------------------------------------------------

def build_decisions(candidates_result: dict, audit_result: dict) -> dict:
    """Build enrichment decisions from candidates."""
    candidates = candidates_result.get("candidates", [])

    by_disposition: dict[str, list[dict]] = {}
    for c in candidates:
        disp = c["disposition"]
        by_disposition.setdefault(disp, []).append(c)

    return {
        "family": candidates_result.get("family", ""),
        "platform": candidates_result.get("platform", ""),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_candidates": len(candidates),
        "denominator": candidates_result.get("denominator", {}),
        "decisions_by_disposition": by_disposition,
        "generate_now": by_disposition.get("generate_now", []),
        "update_existing": by_disposition.get("update_existing", []),
        "deferred": by_disposition.get("deferred_to_backlog", []),
        "rejected": by_disposition.get("rejected_with_reason", []),
        "blocked": by_disposition.get("blocked_with_reason", []),
    }


def build_handoff_manifest(
    decisions: dict,
    family: str,
    platform: str,
    *,
    dry_run: bool = False,
) -> dict:
    """Build a handoff manifest for downstream skill execution."""
    generate_items = decisions.get("generate_now", [])
    update_items = decisions.get("update_existing", [])
    deferred_items = decisions.get("deferred", [])

    manifest_items = []
    for item in generate_items:
        manifest_items.append({
            "action": item["action"],
            "cluster": item["cluster"],
            "subdomain": item["subdomain"],
            "score": item["score"],
            "target_skill": _action_to_skill(item["action"]),
            "dry_run": dry_run,
        })

    for item in update_items:
        manifest_items.append({
            "action": item["action"],
            "cluster": item["cluster"],
            "subdomain": item["subdomain"],
            "score": item["score"],
            "target_skill": _action_to_skill(item["action"]),
            "dry_run": dry_run,
        })

    backlog_items = []
    for item in deferred_items:
        backlog_items.append({
            "cluster": item["cluster"],
            "subdomain": item["subdomain"],
            "reason": item.get("reason", ""),
            "score": item["score"],
        })

    return {
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "dry_run": dry_run,
        "manifest_items": manifest_items,
        "backlog_items": backlog_items,
        "total_manifest": len(manifest_items),
        "total_backlog": len(backlog_items),
    }


def _action_to_skill(action_value: str) -> str:
    """Map candidate action to the skill that should execute it."""
    skill_map = {
        "create_new_docs_page": "S-56",
        "update_existing_docs_page": "S-20",
        "create_new_kb_page": "S-58",
        "update_existing_kb_page": "S-20",
        "create_new_blog_post": "S-57",
        "update_existing_blog_post": "S-20",
    }
    return skill_map.get(action_value, "unknown")
