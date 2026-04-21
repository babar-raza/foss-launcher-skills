"""Decision Engine — determine per-page actions based on evidence state.

Usage:
    python scripts/decide.py {family} {platform}
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import resolve_evidence_root as _resolve_evidence_root

EVIDENCE_ROOT = _resolve_evidence_root()

# Core page types every product should have
CORE_PAGES = [
    {"site_type": "docs", "slug": "installation", "label": "Installation guide"},
    {"site_type": "docs", "slug": "quick-start", "label": "Quick start guide"},
    {"site_type": "blog", "slug": "intro", "label": "Introduction blog post"},
    {"site_type": "kb", "slug": "faq", "label": "FAQ page"},
    {"site_type": "kb", "slug": "howto", "label": "How-to article"},
]


def _read_json(path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_latest_verifications(evidence_dir):
    """Load most recent verification report per page slug."""
    verify_dir = evidence_dir / "verification"
    if not verify_dir.exists():
        return {}

    latest = {}
    for f in sorted(verify_dir.glob("*.json")):
        report = _read_json(f, default=None)
        if not report or not isinstance(report, dict):
            continue
        # Extract slug from filename: {slug}-{timestamp}.json
        name = f.stem
        parts = name.rsplit("-", 1)
        slug = parts[0] if len(parts) >= 2 else name
        # Keep the latest by timestamp
        if slug not in latest or report.get("verified_at", "") > latest[slug].get("verified_at", ""):
            latest[slug] = report

    return latest


def _load_latest_diff(evidence_dir):
    """Load most recent diff, if any."""
    diffs_dir = evidence_dir / "diffs"
    if not diffs_dir.exists():
        return None
    diff_files = sorted(diffs_dir.glob("*.json"))
    if not diff_files:
        return None
    return _read_json(diff_files[-1], default=None)


def _decide_page(page_info, verification, diff, mental_model):
    """Determine action for a single page.

    Returns dict with action, reason, priority, sections_to_update.
    """
    exists = page_info.get("exists", False)
    site_type = page_info.get("site_type", "")
    slug = page_info.get("slug", "")
    path = page_info.get("path")
    is_core = page_info.get("is_core", False)

    # Determine tier from mental model
    tiers = mental_model.get("capability_tiers", {})
    tier1_classes = {t["class"].lower() for t in tiers.get("tier_1_core", [])}
    is_tier1_ref = site_type == "reference" and slug.lower() in tier1_classes

    if not exists:
        priority = 1 if (is_core or is_tier1_ref) else 2
        return {
            "action": "create",
            "reason": f"Page does not exist ({page_info.get('label', slug)})",
            "priority": priority,
            "affected_by_diff": False,
            "verification_result": None,
            "sections_to_update": None,
        }

    # Page exists — check verification
    v_result = verification.get("result") if verification else None
    has_diff_changes = False
    if diff:
        impact = diff.get("impact_summary", {})
        severity = impact.get("severity", "NONE")
        affected_types = impact.get("affected_page_types", [])
        has_diff_changes = severity != "NONE" and site_type in affected_types

    if v_result == "FAIL":
        return {
            "action": "update",
            "reason": f"Verification FAIL: {_summarize_issues(verification)}",
            "priority": 1,
            "affected_by_diff": has_diff_changes,
            "verification_result": "FAIL",
            "sections_to_update": _affected_sections(verification),
        }

    if v_result == "WARN" and has_diff_changes:
        return {
            "action": "update",
            "reason": f"Verification WARN + evidence drift detected",
            "priority": 2,
            "affected_by_diff": True,
            "verification_result": "WARN",
            "sections_to_update": _affected_sections(verification),
        }

    if v_result == "WARN":
        return {
            "action": "enhance",
            "reason": f"Verification WARN: {_summarize_issues(verification)}",
            "priority": 3,
            "affected_by_diff": False,
            "verification_result": "WARN",
            "sections_to_update": None,
        }

    if v_result == "PASS" and has_diff_changes:
        return {
            "action": "verify_only",
            "reason": "Content verified but new evidence available",
            "priority": 2,
            "affected_by_diff": True,
            "verification_result": "PASS",
            "sections_to_update": None,
        }

    if v_result == "PASS":
        return {
            "action": "no_change",
            "reason": "Content verified, no new evidence",
            "priority": 5,
            "affected_by_diff": False,
            "verification_result": "PASS",
            "sections_to_update": None,
        }

    # No verification result — treat as needing verification
    if has_diff_changes:
        return {
            "action": "update",
            "reason": "Unverified page with evidence drift",
            "priority": 2,
            "affected_by_diff": True,
            "verification_result": None,
            "sections_to_update": None,
        }

    return {
        "action": "enhance",
        "reason": "Page exists but has not been verified",
        "priority": 3,
        "affected_by_diff": False,
        "verification_result": None,
        "sections_to_update": None,
    }


def _summarize_issues(verification):
    """Produce a short summary of verification issues."""
    if not verification:
        return "no verification data"
    issues = verification.get("issues", [])
    if not issues:
        return "unknown issues"
    types = {}
    for i in issues:
        t = i.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    return ", ".join(f"{count} {typ}" for typ, count in types.items())


def _affected_sections(verification):
    """Extract section names affected by verification issues."""
    if not verification:
        return None
    issues = verification.get("issues", [])
    # Simple: return issue types as section hints
    sections = list({i.get("type", "") for i in issues if i.get("type")})
    return sections if sections else None


def decide(family, platform):
    """Run decision engine. Returns and writes decision report."""
    evidence_dir = EVIDENCE_ROOT / family / platform
    model_path = evidence_dir / "mental_model.json"

    if not model_path.exists():
        print(f"  SKIP {family}/{platform}: no mental_model.json (run mental_model first)")
        return None

    mental_model = _read_json(model_path)
    verifications = _load_latest_verifications(evidence_dir)
    diff = _load_latest_diff(evidence_dir)

    page_coverage = mental_model.get("page_coverage", {})

    # Build list of pages to evaluate
    pages_to_evaluate = []

    # Core pages
    for core in CORE_PAGES:
        site_cov = page_coverage.get(core["site_type"], {})
        page_state = site_cov.get(core["slug"], {})
        pages_to_evaluate.append({
            "site_type": core["site_type"],
            "slug": core["slug"],
            "label": core["label"],
            "exists": page_state.get("status") == "exists",
            "path": page_state.get("path"),
            "is_core": True,
        })

    # Reference pages for tier-1 classes
    tiers = mental_model.get("capability_tiers", {})
    ref_coverage = page_coverage.get("reference", {})
    for cls_info in tiers.get("tier_1_core", []):
        cls_name = cls_info["class"]
        slug = cls_name.lower()
        page_state = ref_coverage.get(slug, {})
        pages_to_evaluate.append({
            "site_type": "reference",
            "slug": slug,
            "label": f"API reference for {cls_name}",
            "exists": page_state.get("status") == "exists",
            "path": page_state.get("path"),
            "is_core": False,
        })

    # Existing pages not in core list (already published content)
    seen = {(p["site_type"], p["slug"]) for p in pages_to_evaluate}
    for site_type, pages in page_coverage.items():
        for slug, state in pages.items():
            if (site_type, slug) not in seen and state.get("status") == "exists":
                pages_to_evaluate.append({
                    "site_type": site_type,
                    "slug": slug,
                    "label": f"Existing {site_type} page: {slug}",
                    "exists": True,
                    "path": state.get("path"),
                    "is_core": False,
                })

    # Decide per page
    decisions = []
    for page_info in pages_to_evaluate:
        slug = page_info["slug"]
        verification = verifications.get(slug)
        decision = _decide_page(page_info, verification, diff, mental_model)
        decisions.append({
            "site_type": page_info["site_type"],
            "slug": slug,
            "path": page_info.get("path"),
            **decision,
        })

    # Sort by priority
    decisions.sort(key=lambda d: d["priority"])

    # Summary
    summary = {"create": 0, "update": 0, "enhance": 0, "verify_only": 0, "no_change": 0, "total": len(decisions)}
    for d in decisions:
        action = d["action"]
        summary[action] = summary.get(action, 0) + 1

    report = {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "pages": decisions,
        "summary": summary,
    }

    # Write
    decision_path = evidence_dir / "decision.json"
    decision_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  {family}/{platform}: {summary['total']} pages — "
          f"create={summary['create']} update={summary['update']} enhance={summary['enhance']} "
          f"verify_only={summary['verify_only']} no_change={summary['no_change']}")
    return report


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/decide.py {family} {platform}")
        sys.exit(1)

    result = decide(sys.argv[1], sys.argv[2])
    if not result:
        sys.exit(1)

    print("EVIDENCE-DECIDE: PASS")


if __name__ == "__main__":
    main()
