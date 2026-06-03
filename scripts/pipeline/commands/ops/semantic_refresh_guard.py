#!/usr/bin/env python3
"""semantic_refresh_guard.py — Post-update semantic refresh guard (v2).

CONTRACT: scripts/pipeline/commands/ops/semantic_refresh_guard.py
  purpose: After page-update completes, verify that HIGH/MEDIUM/UNKNOWN source changes
           produced appropriate body updates. Blocks refresh acceptance when unproven noops
           detected or when only generated reference pages changed while existing HIGH/MEDIUM
           impacted content pages remained EVIDENCE_ONLY.
           Consumes semantic_source_delta.json (from semantic_source_classifier.py, Step 4.5)
           and page_decisions.json (from refresh_review.py, post page-update).
           Optionally consumes page_impact.json (from page_impact_assess.py) to distinguish
           generated reference pages from existing impacted content pages.
  inputs:  family, platform, --source-delta (REQUIRED), --page-decisions (REQUIRED),
           --page-impact (optional: reports/refresh_review/{family}/{platform}/page_impact.json)
  outputs: reports/refresh_review/{family}/{platform}/semantic_refresh_verdict.json
  idempotent: yes — overwrites on re-run

Exit codes:
  0 = SEMANTIC_NOOP_PROVEN | BODY_UPDATED_VERIFIED | EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED
      | GRADING_REMEDIATION_REQUIRED (accept allowed)
  1 = REFRESH_BLOCKED_UNPROVEN_NOOP | SEMANTIC_REFRESH_REQUIRED
      | GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT (commit blocked)
  2 = CLAIM_EXTRACTION_MISSED_DELTA | PAGE_MAPPING_MISSED_IMPACT (commit blocked)
  4 = GUARD_ERROR_BLOCKED (infra error + HIGH/MEDIUM/UNKNOWN source change — commit blocked)
  5 = GUARD_ERROR_WARN (infra error + source_changed=false or INTERNAL_ONLY — warn only)

Verdict precedence (highest priority wins):
  1. GUARD_ERROR_BLOCKED
  2. CLAIM_EXTRACTION_MISSED_DELTA  (specific: user-facing files + claim_delta=0)
  3. PAGE_MAPPING_MISSED_IMPACT     (specific: claims exist but don't reach pages)
  4. SEMANTIC_REFRESH_REQUIRED      (claim delta > 0, body unchanged)
  5. REFRESH_BLOCKED_UNPROVEN_NOOP  (generic catch-all: body=0, no diagnosis)
  6. GRADING_REMEDIATION_REQUIRED
  7. SEMANTIC_NOOP_PROVEN
  8. GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT  (v2: body changes are reference-only, existing
                                               HIGH/MEDIUM impacted pages remain EVIDENCE_ONLY)
  9. EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED (v2: body changes in existing content pages)
 10. BODY_UPDATED_VERIFIED (fallback when page_impact not available)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_BLOCKING_IMPACTS = {"HIGH", "MEDIUM", "UNKNOWN"}
_PASSING_VERDICTS = {"BODY_UPDATED_VERIFIED", "SEMANTIC_NOOP_PROVEN", "GRADING_REMEDIATION_REQUIRED", "REFRESH_CYCLE_COMPLETE"}
_BLOCKING_VERDICTS = {
    "GUARD_ERROR_BLOCKED",
    "REFRESH_BLOCKED_UNPROVEN_NOOP",
    "CLAIM_EXTRACTION_MISSED_DELTA",
    "PAGE_MAPPING_MISSED_IMPACT",
    "SEMANTIC_REFRESH_REQUIRED",
    "EXISTING_PAGES_PENDING_UPDATE",
}

_VERDICT_EXIT = {
    "BODY_UPDATED_VERIFIED": 0,
    "EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED": 0,
    "SEMANTIC_NOOP_PROVEN": 0,
    "GRADING_REMEDIATION_REQUIRED": 0,
    "INITIAL_REFRESH_ALLOWED": 0,
    "REFRESH_CYCLE_COMPLETE": 0,
    "EXISTING_PAGES_PENDING_UPDATE": 1,
    "SEMANTIC_REFRESH_REQUIRED": 1,
    "REFRESH_BLOCKED_UNPROVEN_NOOP": 1,
    "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT": 1,
    "CLAIM_EXTRACTION_MISSED_DELTA": 2,
    "PAGE_MAPPING_MISSED_IMPACT": 2,
    "GUARD_ERROR_BLOCKED": 4,
    "GUARD_ERROR_WARN": 5,
}

# Subdomains that are generated reference pages — body changes here do NOT satisfy
# the requirement to update existing docs/kb/products/blog impacted content pages.
_GENERATED_REFERENCE_SUBDOMAINS = {"reference.aspose.org"}


def _load_json(path: Path, label: str) -> tuple[dict, str | None]:
    """Load JSON file. Returns (data, error_message)."""
    if not path.is_file():
        return {}, f"{label} not found at {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data or {}, None
    except Exception as e:
        return {}, f"Failed to parse {label}: {e}"


def _count_body_changes(page_decisions: dict) -> tuple[int, int]:
    """Count BODY_UPDATED and frontmatter-only (EVIDENCE_ONLY) decisions."""
    pages = page_decisions.get("pages", {})
    body_changed = sum(1 for v in pages.values() if v.get("body_hash_changed") is True)
    evidence_only = sum(1 for v in pages.values() if v.get("decision") == "EVIDENCE_ONLY")
    return body_changed, evidence_only


def _removed_claims_cited_in_pages(
    removed_claim_ids: list[str],
    family: str,
    platform: str,
    repo_root: Path,
) -> bool:
    """Return True if ANY removed claim ID is cited in a content page for this product.

    Scans all content subdomains for the product. Returns False if no removed claim
    is found in any page file, meaning PAGE_MAPPING_MISSED_IMPACT would be a false
    positive (claims were removed from knowledge but were never cited in pages).
    """
    if not removed_claim_ids:
        return False
    content_root = repo_root / "content"
    sites = [
        content_root / "docs.aspose.org" / "en" / family / platform,
        content_root / "kb.aspose.org" / "en" / family / platform,
        content_root / "blog.aspose.org" / family / platform,
        content_root / "reference.aspose.org" / "en" / family / platform,
        content_root / "products.aspose.org" / "en" / family,
    ]
    claim_id_set = set(removed_claim_ids)
    for site_dir in sites:
        if not site_dir.is_dir():
            continue
        for md_file in site_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                for cid in claim_id_set:
                    if cid in text:
                        return True
            except Exception:
                continue
    return False


def _count_grade_issues(family: str, platform: str, repo_root: Path) -> int:
    """Count D/F graded pages for this product."""
    try:
        lib_dir = str(repo_root / "scripts" / "pipeline")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from lib.grade_writer import read_grade  # type: ignore

        count = 0
        content_root = repo_root / "content"
        for site in ["docs.aspose.org", "kb.aspose.org"]:
            site_dir = content_root / site / "en" / family / platform
            if not site_dir.is_dir():
                continue
            for f in site_dir.rglob("*.md"):
                g = read_grade(f)
                if g and g.get("grade") in ("D", "F"):
                    count += 1
        return count
    except Exception:
        return 0


def _has_user_facing_changes(source_delta: dict) -> bool:
    """True if any classified file is DEFINITELY or PROBABLY user-facing."""
    for f in source_delta.get("files_classified", []):
        if f.get("category") in {"DEFINITELY_USER_FACING", "PROBABLY_USER_FACING"}:
            return True
    return False


def _is_generated_reference_page(path: str) -> bool:
    """True if the page path belongs to the generated reference subdomain."""
    return any(sub in path for sub in _GENERATED_REFERENCE_SUBDOMAINS)


def _classify_body_changes_with_impact(
    page_decisions: dict,
    page_impact: dict,
) -> tuple[int, int, int]:
    """Classify body changes by page kind using page_impact data.

    Returns:
        (existing_content_body_changes, reference_only_body_changes,
         high_medium_existing_evidence_only_count)

    existing_content_body_changes: body changes on docs/kb/products/blog pages
    reference_only_body_changes: body changes on reference.aspose.org pages
    high_medium_existing_evidence_only_count: HIGH/MEDIUM impacted existing content
        pages with EVIDENCE_ONLY decision (i.e., pages that SHOULD have been updated)
    """
    pages = page_decisions.get("pages", {})
    # Build PIA score map: path → pia_score
    pia_map = {}
    for entry in page_impact.get("pages", []):
        pia_map[entry["path"]] = entry.get("pia_score", "LOW_IMPACT")

    existing_body = 0
    ref_body = 0
    hm_existing_eo = 0

    for path, entry in pages.items():
        is_ref = _is_generated_reference_page(path)
        body_changed = entry.get("body_hash_changed", False)
        decision = entry.get("decision", "")
        pia_score = pia_map.get(path, "LOW_IMPACT")

        if body_changed:
            if is_ref:
                ref_body += 1
            else:
                existing_body += 1

        # Count HIGH/MEDIUM existing content pages that are EVIDENCE_ONLY
        if not is_ref and decision == "EVIDENCE_ONLY":
            if pia_score in ("HIGH_IMPACT", "MEDIUM_IMPACT"):
                hm_existing_eo += 1

    return existing_body, ref_body, hm_existing_eo


def evaluate(
    family: str,
    platform: str,
    source_delta: dict,
    page_decisions: dict,
    knowledge_delta: dict,
    *,
    repo_root: Path | None = None,
    page_impact_data: dict | None = None,
) -> tuple[str, str, list[str]]:
    """
    Apply verdict precedence rules (v2).

    Args:
        page_impact_data: Optional dict loaded from page_impact.json.
            When provided, enables GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT detection:
            if body changes are all generated reference pages while existing HIGH/MEDIUM
            impacted content pages remain EVIDENCE_ONLY, the guard blocks.

    Returns (verdict, confidence, proof_list).
    """
    root = repo_root or _REPO_ROOT
    proof: list[str] = list(source_delta.get("proof", []))

    source_changed = source_delta.get("source_changed", True)
    source_impact = source_delta.get("source_change_impact", "UNKNOWN")
    diff_available = source_delta.get("diff_available", False)
    claim_delta_count = source_delta.get("claim_delta_count", 0)
    detail = source_delta.get("claim_delta_detail", {})
    modified_claims = detail.get("modified_claims", 0)
    removed_claims = detail.get("removed_claims", 0)
    modified_apis = detail.get("modified_apis", 0)

    body_changed, evidence_only = _count_body_changes(page_decisions)
    grade_issues = _count_grade_issues(family, platform, root)

    proof.append(f"page_decisions: {body_changed} body_changed, {evidence_only} EVIDENCE_ONLY")
    if grade_issues > 0:
        proof.append(f"grade scan: {grade_issues} D/F pages found")

    has_user_facing = _has_user_facing_changes(source_delta)

    # ── Priority 1: Guard Error Blocked ──────────────────────────────────────
    # (handled in guard() below, not here)

    # ── Priority 2: CLAIM_EXTRACTION_MISSED_DELTA ────────────────────────────
    # Only fires when source has DEFINITELY/PROBABLY user-facing files AND claim delta is 0.
    # Checked before REFRESH_BLOCKED so specific diagnosis wins over generic block.
    if has_user_facing and claim_delta_count == 0 and source_changed:
        proof.append(
            "CLAIM_EXTRACTION_MISSED_DELTA: user-facing source files changed but claim_delta_count=0"
        )
        return "CLAIM_EXTRACTION_MISSED_DELTA", "HIGH", proof

    # ── Priority 3: PAGE_MAPPING_MISSED_IMPACT ────────────────────────────────
    # modified_claims or removed_claims exist but 0 body changes.
    # Before flagging removed_claims, verify they are actually cited in pages.
    # If knowledge_delta provides actual claim IDs AND none are cited in any page,
    # this is a false positive (claims removed from knowledge but never in pages).
    # If knowledge_delta is absent/empty, stay conservative and flag the impact.
    if (removed_claims > 0 or modified_claims > 0) and body_changed == 0:
        removed_claim_ids = knowledge_delta.get("removed_claims", [])
        if (removed_claims > 0
                and removed_claim_ids  # have actual IDs to verify
                and not _removed_claims_cited_in_pages(
                    removed_claim_ids, family, platform, root
                )):
            # Removed claim IDs verified uncited in all pages — not a real missed impact
            proof.append(
                f"PAGE_MAPPING_MISSED_IMPACT skipped: {removed_claims} removed_claims "
                f"verified uncited in all pages (false positive suppressed)"
            )
            # Fall through to later verdicts
        else:
            proof.append(
                f"PAGE_MAPPING_MISSED_IMPACT: {modified_claims} modified_claims + {removed_claims} "
                f"removed_claims exist but 0 body changes in page_decisions"
            )
            return "PAGE_MAPPING_MISSED_IMPACT", "HIGH", proof

    # ── Priority 4: SEMANTIC_REFRESH_REQUIRED ────────────────────────────────
    # claim delta > 0 (any type) but 0 body changes and source is user-facing
    if claim_delta_count > 0 and body_changed == 0 and has_user_facing:
        # ── Priority 4b: INITIAL_REFRESH_ALLOWED ──────────────────────────
        # First-time automated write: no prior harness dispatch recorded.
        # Allows the initial content generation to proceed, breaking the
        # chicken-and-egg deadlock where the guard blocks writes because
        # pages aren't updated, but pages can't update without writes.
        dispatch_state = root / "runs" / "state" / family / platform / "dispatch_history.json"
        if not dispatch_state.exists():
            proof.append(
                f"INITIAL_REFRESH_ALLOWED: claim_delta={claim_delta_count}, body_changed=0, "
                f"but no prior dispatch recorded — allowing first automated write"
            )
            return "INITIAL_REFRESH_ALLOWED", "HIGH", proof

        # ── Priority 4c: EXISTING_PAGES_PENDING_UPDATE ──────────────────
        # Second cycle: dispatch_history exists but pending_page_updates.json
        # lists pages that haven't been updated yet.
        pending_path = root / "runs" / "state" / family / platform / "pending_page_updates.json"
        if dispatch_state.exists() and pending_path.is_file():
            try:
                pending = json.loads(pending_path.read_text(encoding="utf-8"))
                if pending:
                    proof.append(
                        f"EXISTING_PAGES_PENDING_UPDATE: {len(pending)} HIGH/MEDIUM existing pages "
                        f"need agent-assisted update before second refresh cycle"
                    )
                    return "EXISTING_PAGES_PENDING_UPDATE", "MEDIUM", proof
            except (OSError, json.JSONDecodeError):
                pass

        # ── Priority 4d: REFRESH_CYCLE_COMPLETE ───────────────────────────
        # Dispatch history exists, pending is empty (or absent), and
        # freshness manifest is FRESH.  This means the initial refresh
        # cycle completed successfully — pages were regenerated, and no
        # further agent-assisted updates are outstanding.
        manifest_path = (
            root / "runs" / "state" / family / platform
            / "reference" / "freshness-manifest.json"
        )
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("manifest_status") == "FRESH":
                    proof.append(
                        f"REFRESH_CYCLE_COMPLETE: dispatch_history exists, "
                        f"pending_page_updates empty, freshness manifest FRESH "
                        f"(run_id={manifest.get('run_id', 'unknown')})"
                    )
                    return "REFRESH_CYCLE_COMPLETE", "HIGH", proof
            except (OSError, json.JSONDecodeError):
                pass  # Fall through to SEMANTIC_REFRESH_REQUIRED

        proof.append(
            f"SEMANTIC_REFRESH_REQUIRED: claim_delta_count={claim_delta_count}, body_changed=0, "
            f"user-facing source changes present"
        )
        return "SEMANTIC_REFRESH_REQUIRED", "MEDIUM", proof

    # ── Priority 5: REFRESH_BLOCKED_UNPROVEN_NOOP ────────────────────────────
    # Generic catch-all: HIGH/MEDIUM/UNKNOWN impact + body=0 with no more specific diagnosis
    if (source_changed and source_impact in _BLOCKING_IMPACTS and body_changed == 0
            and source_impact != "INTERNAL_ONLY"):
        # Check if we have proof it's internal-only
        internal_proof = any(
            "INTERNAL_ONLY" in p or "TEST_ONLY" in p or "BUILD_ONLY" in p
            for p in proof
        )
        if not internal_proof or not diff_available:
            proof.append(
                f"BLOCKED: source_impact={source_impact}, body_changed=0, no internal-only proof"
            )
            return "REFRESH_BLOCKED_UNPROVEN_NOOP", "HIGH", proof

    # ── Priority 6: GRADING_REMEDIATION_REQUIRED ─────────────────────────────
    if grade_issues > 0:
        proof.append(f"GRADING_REMEDIATION_REQUIRED: {grade_issues} D/F pages need remediation")
        return "GRADING_REMEDIATION_REQUIRED", "HIGH", proof

    # ── Priority 7: SEMANTIC_NOOP_PROVEN ─────────────────────────────────────
    if source_impact == "INTERNAL_ONLY" and diff_available:
        proof.append("SEMANTIC_NOOP_PROVEN: all changed files are TEST_ONLY/BUILD_ONLY/DOC_ONLY_UPSTREAM")
        return "SEMANTIC_NOOP_PROVEN", "HIGH", proof

    if not source_changed:
        proof.append("SEMANTIC_NOOP_PROVEN: source_changed=false")
        return "SEMANTIC_NOOP_PROVEN", "HIGH", proof

    # ── Priority 8: GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT (v2) ─────────────
    # Fires when page_impact is available AND:
    #   - body_changed > 0 (guard would normally pass)
    #   - ALL body changes are on generated reference pages
    #   - Existing HIGH/MEDIUM impacted content pages are EVIDENCE_ONLY
    # This catches the font/python masking defect.
    if body_changed > 0 and page_impact_data is not None:
        existing_body, ref_body, hm_eo = _classify_body_changes_with_impact(
            page_decisions, page_impact_data
        )
        proof.append(
            f"page_impact analysis: {existing_body} existing-content body changes, "
            f"{ref_body} generated-reference body changes, "
            f"{hm_eo} HIGH/MEDIUM existing pages EVIDENCE_ONLY"
        )
        if existing_body == 0 and ref_body > 0 and hm_eo > 0:
            proof.append(
                f"GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT: {ref_body} generated reference "
                f"pages changed but {hm_eo} HIGH/MEDIUM impacted existing content pages "
                f"remain EVIDENCE_ONLY — generated reference changes do not satisfy "
                f"the existing content update requirement"
            )
            return "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT", "HIGH", proof

        # ── Priority 9: EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED ─────────────
        # Fires when existing content pages have body changes (with page_impact available)
        if existing_body > 0:
            proof.append(
                f"EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED: {existing_body} existing content "
                f"pages had body changes ({hm_eo} HIGH/MEDIUM impacted pages remain EVIDENCE_ONLY)"
            )
            return "EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED", "HIGH", proof

    # ── Priority 10: BODY_UPDATED_VERIFIED ───────────────────────────────────
    # Fallback when page_impact not available: any body change satisfies
    if body_changed > 0:
        proof.append(f"BODY_UPDATED_VERIFIED: {body_changed} pages had body changes")
        return "BODY_UPDATED_VERIFIED", "HIGH", proof

    # Fallback: can't determine
    proof.append("REFRESH_BLOCKED_UNPROVEN_NOOP: could not verify semantic noop")
    return "REFRESH_BLOCKED_UNPROVEN_NOOP", "LOW", proof


def guard(
    family: str,
    platform: str,
    *,
    source_delta_path: Path,
    page_decisions_path: Path,
    knowledge_delta_path: Path | None = None,
    page_impact_path: Path | None = None,
    out_path: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[dict, int]:
    """
    Run the post-update semantic guard.

    Returns (verdict_dict, exit_code).
    """
    root = repo_root or _REPO_ROOT

    if out_path is None:
        out_path = root / "reports" / "refresh_review" / family / platform / "semantic_refresh_verdict.json"

    verdict_result: dict = {
        "family": family,
        "platform": platform,
        "old_source_sha": "",
        "new_source_sha": "",
        "source_changed": True,
        "source_change_impact": "UNKNOWN",
        "body_changes_count": 0,
        "frontmatter_only_changes_count": 0,
        "claim_delta_count": 0,
        "grade_issue_count": 0,
        "verdict": "GUARD_ERROR_BLOCKED",
        "verdict_confidence": "LOW",
        "proof": [],
        "guard_error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Load source delta (REQUIRED)
    source_delta, err1 = _load_json(source_delta_path, "source_delta")
    page_decisions, err2 = _load_json(page_decisions_path, "page_decisions")

    # Determine source impact for fail-closed logic
    source_impact = source_delta.get("source_change_impact", "UNKNOWN") if source_delta else "UNKNOWN"
    source_changed = source_delta.get("source_changed", True) if source_delta else True

    # Infrastructure errors — apply fail-closed rules
    if err1 or err2:
        errors = [e for e in [err1, err2] if e]
        guard_error = "; ".join(errors)
        verdict_result["guard_error"] = guard_error

        is_blocking = source_changed and source_impact in _BLOCKING_IMPACTS
        if is_blocking:
            verdict_result["verdict"] = "GUARD_ERROR_BLOCKED"
            verdict_result["proof"] = [f"Guard infrastructure error (blocking): {guard_error}"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(verdict_result, indent=2), encoding="utf-8")
            return verdict_result, 4
        else:
            verdict_result["verdict"] = "GUARD_ERROR_WARN"
            verdict_result["proof"] = [f"Guard infrastructure error (warn only): {guard_error}"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(verdict_result, indent=2), encoding="utf-8")
            return verdict_result, 5

    # Load optional knowledge delta
    knowledge_delta: dict = {}
    if knowledge_delta_path and knowledge_delta_path.is_file():
        knowledge_delta, _ = _load_json(knowledge_delta_path, "knowledge_delta")

    # Load optional page_impact (v2: enables GENERATED_ONLY detection)
    page_impact_data: dict | None = None
    if page_impact_path is None:
        # Try auto-discovery: look for page_impact.json alongside page_decisions.json
        auto_pi = page_decisions_path.parent / "page_impact.json"
        if auto_pi.is_file():
            page_impact_data, _ = _load_json(auto_pi, "page_impact")
    elif page_impact_path.is_file():
        page_impact_data, _ = _load_json(page_impact_path, "page_impact")

    # Populate base fields
    verdict_result["old_source_sha"] = source_delta.get("old_source_sha", "")
    verdict_result["new_source_sha"] = source_delta.get("new_source_sha", "")
    verdict_result["source_changed"] = source_delta.get("source_changed", True)
    verdict_result["source_change_impact"] = source_impact
    verdict_result["claim_delta_count"] = source_delta.get("claim_delta_count", 0)

    body_changed, evidence_only = _count_body_changes(page_decisions)
    verdict_result["body_changes_count"] = body_changed
    verdict_result["frontmatter_only_changes_count"] = evidence_only

    grade_issues = _count_grade_issues(family, platform, root)
    verdict_result["grade_issue_count"] = grade_issues

    # Evaluate verdict
    try:
        verdict, confidence, proof = evaluate(
            family, platform, source_delta, page_decisions, knowledge_delta,
            repo_root=root, page_impact_data=page_impact_data,
        )
    except Exception as e:
        guard_error = f"evaluate() raised exception: {e}"
        verdict_result["guard_error"] = guard_error
        verdict_result["proof"] = [guard_error]
        if source_changed and source_impact in _BLOCKING_IMPACTS:
            verdict_result["verdict"] = "GUARD_ERROR_BLOCKED"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(verdict_result, indent=2), encoding="utf-8")
            return verdict_result, 4
        else:
            verdict_result["verdict"] = "GUARD_ERROR_WARN"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(verdict_result, indent=2), encoding="utf-8")
            return verdict_result, 5

    verdict_result["verdict"] = verdict
    verdict_result["verdict_confidence"] = confidence
    verdict_result["proof"] = proof

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(verdict_result, indent=2), encoding="utf-8")

    exit_code = _VERDICT_EXIT.get(verdict, 4)
    return verdict_result, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-update semantic refresh guard for S-84 Step 11.5"
    )
    parser.add_argument("family", help="Product family (e.g. font, cells)")
    parser.add_argument("platform", help="Platform (e.g. python, java)")
    parser.add_argument(
        "--source-delta", required=True,
        help="Path to semantic_source_delta.json (from semantic_source_classifier.py)"
    )
    parser.add_argument(
        "--source-classification", default=None,
        help="Alias for --source-delta (backward compat)"
    )
    parser.add_argument(
        "--page-decisions", required=True,
        help="Path to page_decisions.json (post page-update)"
    )
    parser.add_argument(
        "--knowledge-delta", default=None,
        help="Path to knowledge_delta.json (optional cross-check)"
    )
    parser.add_argument(
        "--page-impact", default=None,
        help="Path to page_impact.json (optional; enables GENERATED_ONLY detection). "
             "If omitted, auto-discovered alongside page-decisions."
    )
    parser.add_argument("--out", default=None, help="Output path for semantic_refresh_verdict.json")
    parser.add_argument("--repo-root", default=None, help="Override repository root")
    args = parser.parse_args(argv)

    # --source-classification is alias for --source-delta
    source_delta_str = args.source_delta or args.source_classification
    if not source_delta_str:
        print("ERROR: --source-delta is required", file=sys.stderr)
        return 4

    source_delta_path = Path(source_delta_str)
    page_decisions_path = Path(args.page_decisions)
    repo_root = Path(args.repo_root) if args.repo_root else None
    out_path = Path(args.out) if args.out else None

    kd_path: Path | None = None
    if args.knowledge_delta:
        kd_path = Path(args.knowledge_delta)

    pi_path: Path | None = None
    if args.page_impact:
        pi_path = Path(args.page_impact)

    _, exit_code = guard(
        family=args.family,
        platform=args.platform,
        source_delta_path=source_delta_path,
        page_decisions_path=page_decisions_path,
        knowledge_delta_path=kd_path,
        page_impact_path=pi_path,
        out_path=out_path,
        repo_root=repo_root,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
