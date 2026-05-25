"""semantic_body_update_planner.py — Report-only planner for semantic body updates.

Given source delta, guard verdict, page_impact, knowledge_delta, and page_decisions,
selects HIGH/MEDIUM impacted EXISTING (non-reference) pages that require body updates
and proposes S-73 scope/section/intent for each.

Exit codes:
  0 = plan written (may include 0 actionable pages — see plan for details)
  1 = blocked: missing required artifact
  2 = no impacted existing pages found (either not staged or all reference stubs)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_GENERATED_REFERENCE_SUBDOMAINS = {"reference.aspose.org"}

_SUBDOMAIN_PRIORITY = {
    "docs.aspose.org": 1,
    "kb.aspose.org": 2,
    "products.aspose.org": 3,
    "blog.aspose.org": 4,
    "reference.aspose.org": 99,
}

_DECISION_BODY_UPDATE_REQUIRED = "BODY_UPDATE_REQUIRED"
_DECISION_SEMANTIC_NOOP_PROVEN = "SEMANTIC_NOOP_PROVEN"
_DECISION_CLAIM_EXTRACTION_GAP = "CLAIM_EXTRACTION_GAP"
_DECISION_PAGE_MAPPING_GAP = "PAGE_MAPPING_GAP"
_DECISION_SOURCE_EVIDENCE_UNAVAILABLE = "SOURCE_EVIDENCE_UNAVAILABLE"

_ALL_ZERO_SHA = "0" * 40


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _is_generated_reference_page(path: str) -> bool:
    return any(sub in path for sub in _GENERATED_REFERENCE_SUBDOMAINS)


def _subdomain_from_path(path: str) -> str:
    for sub in _SUBDOMAIN_PRIORITY:
        if sub in path:
            return sub
    return "unknown"


def _page_priority(path: str) -> int:
    return _SUBDOMAIN_PRIORITY.get(_subdomain_from_path(path), 50)


def _load_json(path: Path, label: str) -> dict | list | None:
    if not path.exists():
        print(f"WARN: {label} not found at {path}", file=sys.stderr)
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_claim_delta(knowledge_delta_path: Path) -> dict:
    delta = _load_json(knowledge_delta_path, "knowledge_delta")
    if delta is None:
        return {"new_claims": [], "modified_claims": [], "removed_claims": []}
    return {
        "new_claims": delta.get("new_claims", []),
        "modified_claims": delta.get("modified_claims", []),
        "removed_claims": delta.get("removed_claims", []),
    }


def _load_api_delta(source_delta: dict) -> dict:
    return source_delta.get("claim_delta_detail", {})


def _propose_s73(signals: list[str], claim_delta: dict) -> dict:
    new_n = len(claim_delta.get("new_claims", []))
    rem_n = len(claim_delta.get("removed_claims", []))
    mod_n = len(claim_delta.get("modified_claims", []))
    api_signals = [s.removeprefix("api:") for s in signals if s.startswith("api:")]

    if rem_n > 0:
        intent = (
            f"Remove or update references to removed APIs/behaviors "
            f"({rem_n} removed claims) for: {', '.join(api_signals[:3])}"
        )
    elif new_n > 0 and api_signals:
        intent = (
            f"Add brief mention of new capabilities "
            f"({new_n} new claims) for: {', '.join(api_signals[:3])}"
        )
    elif mod_n > 0:
        intent = (
            f"Update description to reflect modified API behavior "
            f"({mod_n} modified claims) for: {', '.join(api_signals[:3])}"
        )
    else:
        intent = (
            f"Verify and update content accuracy for: {', '.join(api_signals[:3])}"
        )

    return {
        "scope": "body-wording",
        "section": None,
        "intent_template": intent,
        "api_signals": api_signals,
        "confidence": "MEDIUM" if api_signals else "LOW",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Core planner
# ──────────────────────────────────────────────────────────────────────────────

def plan(
    family: str,
    platform: str,
    source_delta_path: Path,
    page_impact_path: Path,
    knowledge_delta_path: Path,
    page_decisions_path: Path,
    max_pages: int,
    include_reference: bool,
) -> dict:
    page_impact = _load_json(page_impact_path, "page_impact")
    if page_impact is None:
        return {"status": "BLOCKED", "reason": f"page_impact.json missing: {page_impact_path}", "pages": []}

    page_decisions = _load_json(page_decisions_path, "page_decisions")
    if page_decisions is None:
        return {"status": "BLOCKED", "reason": f"page_decisions.json missing: {page_decisions_path}", "pages": []}

    source_delta = _load_json(source_delta_path, "source_delta") or {}
    claim_delta = _load_claim_delta(knowledge_delta_path)
    api_delta = _load_api_delta(source_delta)

    old_sha = source_delta.get("old_source_sha", "")
    source_baseline_missing = (old_sha == _ALL_ZERO_SHA or old_sha == "")
    diff_available = source_delta.get("diff_available", False)

    decisions = page_decisions.get("pages", {})
    impact_pages = page_impact.get("pages", [])

    # Filter candidates: non-reference, HIGH/MEDIUM, not already body-updated
    candidates = []
    for entry in impact_pages:
        path = entry.get("path", "")
        score = entry.get("pia_score", "LOW_IMPACT")
        if score not in ("HIGH_IMPACT", "MEDIUM_IMPACT"):
            continue
        if not include_reference and _is_generated_reference_page(path):
            continue
        page_dec = decisions.get(path, {})
        if page_dec.get("body_hash_changed", False):
            continue
        candidates.append({
            "path": path,
            "pia_score": score,
            "signals": entry.get("signals_found", []),
            "decision": page_dec.get("decision", "UNKNOWN"),
            "priority": _page_priority(path),
        })

    candidates.sort(key=lambda x: (x["priority"], 0 if x["pia_score"] == "HIGH_IMPACT" else 1))
    selected = candidates[:max_pages]

    new_n = len(claim_delta.get("new_claims", []))
    rem_n = len(claim_delta.get("removed_claims", []))
    mod_n = len(claim_delta.get("modified_claims", []))

    page_plans = []
    for cand in selected:
        signals = cand["signals"]
        s73 = _propose_s73(signals, claim_delta)

        if source_baseline_missing and not diff_available:
            decision = _DECISION_SOURCE_EVIDENCE_UNAVAILABLE
            rationale = "SOURCE_BASELINE_MISSING: old_source_sha all-zero; diff unavailable"
        elif not signals:
            decision = _DECISION_PAGE_MAPPING_GAP
            rationale = "No API signals found for page — cannot identify update target"
        elif new_n == 0 and rem_n == 0 and mod_n == 0:
            decision = _DECISION_CLAIM_EXTRACTION_GAP
            rationale = "No claim delta — source change not extracted into claims"
        else:
            decision = _DECISION_BODY_UPDATE_REQUIRED
            rationale = (
                f"Page impacted ({cand['pia_score']}); signals={signals[:3]}; "
                f"claim delta: +{new_n}/-{rem_n}/~{mod_n}"
            )

        page_plans.append({
            "path": cand["path"],
            "subdomain": _subdomain_from_path(cand["path"]),
            "pia_score": cand["pia_score"],
            "current_decision": cand["decision"],
            "signals_found": signals,
            "per_page_decision": decision,
            "rationale": rationale,
            "s73_proposal": s73,
            "claim_delta_summary": {"new": new_n, "modified": mod_n, "removed": rem_n},
            "api_delta_summary": api_delta,
        })

    actionable = [p for p in page_plans if p["per_page_decision"] == _DECISION_BODY_UPDATE_REQUIRED]
    source_gap = [p for p in page_plans if p["per_page_decision"] == _DECISION_SOURCE_EVIDENCE_UNAVAILABLE]
    map_gap = [p for p in page_plans if p["per_page_decision"] == _DECISION_PAGE_MAPPING_GAP]
    claim_gap = [p for p in page_plans if p["per_page_decision"] == _DECISION_CLAIM_EXTRACTION_GAP]

    if not page_plans:
        status = "NO_IMPACTED_EXISTING_PAGES"
    elif actionable:
        status = "BODY_UPDATES_PLANNED"
    elif source_gap:
        status = "SOURCE_EVIDENCE_UNAVAILABLE"
    elif map_gap or claim_gap:
        status = "GAP_CLASSIFIED"
    else:
        status = "CLASSIFIED"

    return {
        "family": family,
        "platform": platform,
        "old_source_sha": old_sha,
        "source_baseline_missing": source_baseline_missing,
        "diff_available": diff_available,
        "total_candidates_found": len(candidates),
        "pages_selected": len(page_plans),
        "actionable_count": len(actionable),
        "source_gap_count": len(source_gap),
        "mapping_gap_count": len(map_gap),
        "claim_gap_count": len(claim_gap),
        "overall_status": status,
        "pages": page_plans,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _default_path(family: str, platform: str, filename: str) -> Path:
    return Path("reports") / "refresh_review" / family / platform / filename


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Semantic body-update planner — report-only")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--source-delta", type=Path)
    parser.add_argument("--semantic-verdict", type=Path)
    parser.add_argument("--page-impact", type=Path)
    parser.add_argument("--knowledge-delta", type=Path)
    parser.add_argument("--page-decisions", type=Path)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--include-reference", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    family, platform = args.family, args.platform
    source_delta = args.source_delta or _default_path(family, platform, "semantic_source_delta.json")
    page_impact = args.page_impact or _default_path(family, platform, "page_impact.json")
    knowledge_delta = (args.knowledge_delta or
                       Path("knowledge") / family / platform / "merged" / "knowledge_delta.json")
    page_decisions = args.page_decisions or _default_path(family, platform, "page_decisions.json")
    out = args.out or _default_path(family, platform, "semantic_body_update_plan.json")

    for label, path in [("page_impact", page_impact), ("page_decisions", page_decisions)]:
        if not path.exists():
            print(f"ERROR: required artifact missing — {label}: {path}", file=sys.stderr)
            return 1

    result = plan(
        family=family, platform=platform,
        source_delta_path=source_delta, page_impact_path=page_impact,
        knowledge_delta_path=knowledge_delta, page_decisions_path=page_decisions,
        max_pages=args.max_pages, include_reference=args.include_reference,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Plan written to {out}")
    print(f"Status: {result.get('overall_status', 'UNKNOWN')}")
    print(f"Candidates: {result.get('total_candidates_found', 0)}, Selected: {result.get('pages_selected', 0)}, Actionable: {result.get('actionable_count', 0)}")

    if result.get("status") == "BLOCKED":
        print(f"BLOCKED: {result.get('reason')}", file=sys.stderr)
        return 1
    if result.get("overall_status") == "NO_IMPACTED_EXISTING_PAGES":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
