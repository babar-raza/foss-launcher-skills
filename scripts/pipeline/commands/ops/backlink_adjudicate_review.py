"""
backlink_adjudicate_review.py — Three-Tier Adjudication for REVIEW_REQUIRED candidates

Tier 1: Deterministic (single verified variant, explicit override, exact slug HTTP 200)
Tier 2: AI-assisted (LLMRouter classification, advisory only)
Tier 3: Operator escalation (human review packet for ambiguous cases)

Modes:
    --dry-run (default): Report only, no authority writes
    --write:             Promote qualifying RR records to AUTO_APPROVE_EXACT in authority

Usage:
    # Report only (default):
    .venv/Scripts/python backlink_adjudicate_review.py \\
        --candidate-graph data/backlinks/workspace/candidate_graph.json \\
        --authority data/backlinks/workspace/backlink_authority.json

    # Write promotions to authority:
    .venv/Scripts/python backlink_adjudicate_review.py \\
        --authority data/backlinks/workspace/backlink_authority.json \\
        --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import (
    PLATFORM_ALIASES,
    compute_anchor_config_hash,
    load_anchor_registry,
    render_anchor_text,
    select_anchor_template_id,
)

CANDIDATE_GRAPH_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "candidate_graph.json"
AUTHORITY_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "backlink_authority.json"
ADJUDICATION_REPORT_PATH = REPO_ROOT / "reports" / "backlinks" / "adjudication"
FAMILIES_PATH = REPO_ROOT / "data" / "families.json"
METRICS_TAXONOMY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml"

POLICY_VERSION = "1.0.0"

# Closed-set AI labels
VALID_AI_LABELS = frozenset({
    "exact_api_class", "related_api_class", "same_topic",
    "weakly_related", "unrelated",
})

# CS-013: adjudication-time LLM classification
CALLSITE_AI_ADJUDICATE = "CS-013"

_PROVIDER_UNAVAILABLE_STATUSES = frozenset({
    "not_configured", "unreachable", "auth_failed",
    "model_missing", "disabled_policy", "intentional_skip",
})

_ADJUDICATION_PROMPT = """\
You are classifying the relationship between an aspose.org source page and an aspose.com target API endpoint.

Source: {source_title} ({source_family}/{source_platform})
Target: {target_path}

Classify the relationship as exactly one of:
- exact_api_class: Target is the direct enterprise API reference for this source page
- related_api_class: Target is a related class in the same namespace/family
- same_topic: Target covers the same topic but different type
- weakly_related: Some topical overlap but not a direct match
- unrelated: No meaningful relationship

Respond with JSON only: {{"label": "...", "confidence": "high|medium|low", "reasoning": "one sentence"}}"""


def _try_import_llm_router():
    """Try to import and instantiate LLMRouter; return None if unavailable."""
    try:
        from commands.ops.llm_router import LLMRouter  # type: ignore
        return LLMRouter()
    except Exception:
        return None


# ── Helpers shared with backlink_approve_authority.py ─────────────────────────

_SUBDOMAIN_TO_HOST = {
    "reference": "reference.aspose.com",
    "kb": "kb.aspose.com",
    "docs": "docs.aspose.com",
    "products": "products.aspose.com",
    "blog": "blog.aspose.com",
}

_SOURCE_SD_TO_TARGET_SD = {
    "reference.aspose.org": "reference",
    "kb.aspose.org": "kb",
    "docs.aspose.org": "docs",
    "products.aspose.org": "products",
    "blog.aspose.org": "blog",
}


def _infer_subdomain(source_subdomain: str, target_path: str) -> str:
    """Infer target subdomain from source subdomain."""
    return _SOURCE_SD_TO_TARGET_SD.get(source_subdomain, "reference")


def _infer_target_type(target_path: str, subdomain: str) -> str:
    """Infer target type from path depth and subdomain."""
    parts = target_path.strip("/").split("/")
    if subdomain == "reference":
        if len(parts) >= 4:
            return "reference_class"
        if len(parts) >= 3:
            return "reference_namespace"
        return "platform_landing"
    if subdomain == "kb":
        if len(parts) >= 3:
            return "kb_article"
        return "platform_landing"
    return "platform_landing"


def _compute_source_hash(source: dict) -> str:
    """Compute a stable hash for a source record."""
    canonical = json.dumps({
        "source_key": source.get("source_key", ""),
        "source_path": source.get("source_path", ""),
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _load_families_map() -> dict:
    """Load data/families.json -> {family_key: display_name}."""
    if FAMILIES_PATH.exists():
        raw = json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {item["key"]: item.get("title", item["key"].title()) for item in raw if "key" in item}
        if isinstance(raw, dict):
            return raw
    return {}


def _load_platforms_map() -> dict:
    """Load metrics_taxonomy.yaml platforms block -> {platform_key: display_name}."""
    if METRICS_TAXONOMY_PATH.exists():
        try:
            import yaml
            data = yaml.safe_load(METRICS_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
            return data.get("platforms", {})
        except Exception:
            pass
    return {
        "net": ".NET", "java": "Java", "cpp": "C++", "python": "Python",
        "nodejs": "Node.js", "go": "Go", "android": "Android", "php": "PHP",
        "ruby": "Ruby",
    }


def promote_to_authority(
    promoted: list[dict],
    candidate_graph: dict,
    authority: dict,
    *,
    anchor_registry: Optional[dict] = None,
    families_map: Optional[dict] = None,
    platforms_map: Optional[dict] = None,
) -> dict:
    """
    Promote adjudicated REVIEW_REQUIRED records to AUTO_APPROVE_EXACT in authority.

    Pure business logic — no I/O.

    Args:
        promoted: List of promoted result dicts from adjudicate_review_required()
        candidate_graph: Full candidate graph (for source lookup)
        authority: Existing authority dict (mutated in place)
        anchor_registry: Anchor text registry for rendering
        families_map: Family display names
        platforms_map: Platform display names

    Returns: {promoted_count, skipped_count, errors}
    """
    if families_map is None:
        families_map = {}
    if platforms_map is None:
        platforms_map = {}

    # Build lookup: source_key -> source record
    sources_by_key = {s.get("source_key", ""): s for s in candidate_graph.get("sources", [])}
    # Build lookup: source_key -> best candidate record
    candidates_by_key: dict = {}
    for c in candidate_graph.get("candidates", []):
        sk = c.get("source_key", "")
        if sk not in candidates_by_key or c.get("final_score", 0.0) > candidates_by_key[sk].get("final_score", 0.0):
            candidates_by_key[sk] = c

    anchor_config_hash = None
    if anchor_registry is not None:
        try:
            anchor_config_hash = compute_anchor_config_hash()
        except Exception:
            anchor_config_hash = "sha256:unavailable"

    target_index_hash = candidate_graph.get("deep_index_hash", "sha256:unknown")
    auth_records = authority.setdefault("authority", {})
    now = datetime.now(timezone.utc).isoformat()

    promoted_count = 0
    skipped_count = 0
    errors: list[str] = []
    skipped: list[dict] = []

    for p in promoted:
        source_key = p.get("source_key", "")
        source = sources_by_key.get(source_key)
        candidate = candidates_by_key.get(source_key)
        if source is None or candidate is None:
            errors.append(f"Source/candidate not found for {source_key}")
            skipped_count += 1
            continue

        source_path = source.get("source_path", "")
        family = source.get("family", "")
        platform = source.get("platform") or ""
        subdomain = source.get("subdomain", "")

        raw_target_path = candidate.get("target_path", "")
        target_subdomain = _infer_subdomain(subdomain, raw_target_path)

        # Strip subdomain prefix from target_path if present
        sd_prefix = target_subdomain + "/"
        if raw_target_path.startswith(sd_prefix):
            target_path = raw_target_path[len(sd_prefix):]
        else:
            target_path = raw_target_path

        # Compute anchor text
        rendered_anchor = None
        template_id = None
        rendered_source = None
        if anchor_registry is not None:
            try:
                canonical_plat = PLATFORM_ALIASES.get(platform, platform) if platform else platform
                target_url = f"https://{_SUBDOMAIN_TO_HOST.get(target_subdomain, 'reference.aspose.com')}/{target_path}/"
                target_type = _infer_target_type(target_path, target_subdomain)
                template_id = select_anchor_template_id(
                    target_url, target_type, subdomain,
                )
                rendered_anchor = render_anchor_text(
                    template_id=template_id,
                    family=family,
                    platform=canonical_plat or None,
                    target_url=target_url,
                    registry=anchor_registry,
                    families_map=families_map,
                    platforms_map=platforms_map,
                )
                rendered_source = f"anchor_text_registry.yaml:templates.{template_id}"
            except Exception as exc:
                rendered_anchor = f"Aspose.{family.title()} — Enterprise Reference"
                rendered_source = f"fallback:{exc}"

        if rendered_anchor is None:
            skipped.append({"source_key": source_key, "reason": "null_anchor_text"})
            skipped_count += 1
            continue

        auth_records[source_path] = {
            "source_path": source_path,
            "source_key": source_key,
            "family": family,
            "platform": platform,
            "target_path": target_path,
            "target_subdomain": target_subdomain,
            "decision": "AUTO_APPROVE_EXACT",
            "score": candidate.get("final_score", 0.0),
            "stage1_score": candidate.get("stage1_score", 0.0),
            "ai_boost": candidate.get("ai_boost", 0.0),
            "allowed_for_generation": True,
            "adjudication_result": p.get("adjudication_result", "PROMOTE_WITH_JUSTIFICATION"),
            "adjudicated_from": "REVIEW_REQUIRED",
            "anchor_template_id": template_id,
            "anchor_config_hash": anchor_config_hash,
            "rendered_anchor_text": rendered_anchor,
            "rendered_anchor_source": rendered_source,
            "source_hash": _compute_source_hash(source),
            "target_index_hash": target_index_hash,
            "policy_version": POLICY_VERSION,
            "approved_at": now,
            "freshness_status": "FRESH",
        }
        promoted_count += 1

    return {
        "promoted_count": promoted_count,
        "skipped_count": skipped_count,
        "errors": errors,
        "skipped": skipped,
    }


def _tier2_ai_adjudicate(
    candidates: list[dict],
    *,
    dry_run: bool = True,
    promote_threshold: float = 0.70,
) -> list[dict]:
    """
    Tier 2: AI-assisted adjudication (CS-013).

    When dry_run=True: skips LLM call; uses score-based decisions only
    (ai_status: AI_EXPLICITLY_DISABLED).

    When dry_run=False: calls LLMRouter (gpt-oss, CS-013) to classify each candidate.
    If AI unavailable or raises: falls back to score-based logic
    (ai_status: AI_UNAVAILABLE_DEGRADED) — graceful degradation, no crash.

    Score boost rules (base score >= 0.85 required):
      exact_api_class  → +0.05
      related_api_class → +0.03

    AI override rules (applied before score-based fallback):
      unrelated + score >= 0.80  → ESCALATE_TO_OPERATOR (mandatory human check)
      exact/related_api_class + score < promote_threshold → ESCALATE_TO_OPERATOR
        (surfaces 0.55 dead-zone candidates to Tier 3 instead of silently REJECTing)

    Args:
        promote_threshold: Minimum effective_score for PROMOTE_WITH_JUSTIFICATION (default 0.70).

    Returns list of adjudication result dicts.
    """
    router = None
    if not dry_run:
        router = _try_import_llm_router()

    results = []
    for c in candidates:
        source_key = c.get("source_key", "")
        target_path = c.get("target_path", "")
        base_score = c.get("final_score", 0.0)

        result = {
            "source_key": source_key,
            "target_path": target_path,
            "original_decision": c.get("decision", ""),
            "tier": 2,
            "ai_label": None,
            "ai_confidence": None,
            "adjudication_result": None,
            "ai_status": "AI_EXPLICITLY_DISABLED" if dry_run else "AI_UNAVAILABLE_DEGRADED",
        }

        effective_score = base_score
        ai_label = None

        if not dry_run and router is not None:
            # Derive source context from source_key path (e.g. "docs/cells/java/page.md")
            parts = source_key.replace("\\", "/").split("/")
            source_title = parts[-1].replace(".md", "").replace("-", " ").title() if parts else source_key
            source_family = parts[1] if len(parts) > 1 else "unknown"
            source_platform = parts[2] if len(parts) > 2 else "unknown"

            prompt = _ADJUDICATION_PROMPT.format(
                source_title=source_title,
                source_family=source_family,
                source_platform=source_platform,
                target_path=target_path,
            )
            system_prompt = (
                "You are a classification assistant for API documentation relationships. "
                "Respond with JSON only, using exactly the format requested."
            )
            try:
                llm_result = router.call_chat(
                    system_prompt, prompt, temperature=0.0, max_tokens=500,
                )
                raw_status = getattr(llm_result, "status", None)
                status_val = (
                    raw_status.value
                    if hasattr(raw_status, "value")
                    else str(raw_status).lower()
                )
                if status_val == "ok":
                    raw_data = getattr(llm_result, "data", None)
                    if isinstance(raw_data, dict):
                        parsed = raw_data
                    elif raw_data is not None:
                        import re as _re
                        m = _re.search(r"\{.*?\}", str(raw_data), _re.DOTALL)
                        parsed = json.loads(m.group(0)) if m else {}
                    else:
                        parsed = {}
                    label = parsed.get("label", "")
                    if label in VALID_AI_LABELS:
                        ai_label = label
                        result["ai_label"] = ai_label
                        result["ai_confidence"] = parsed.get("confidence", "low")
                        result["ai_status"] = "AI_CLASSIFIED"
                        # Score boost (only when base score meets eligibility threshold)
                        if base_score >= 0.85:
                            if ai_label == "exact_api_class":
                                effective_score = min(base_score + 0.05, 1.0)
                            elif ai_label == "related_api_class":
                                effective_score = min(base_score + 0.03, 1.0)
                elif status_val in _PROVIDER_UNAVAILABLE_STATUSES:
                    result["ai_status"] = "AI_UNAVAILABLE_DEGRADED"
                else:
                    result["ai_status"] = "AI_UNAVAILABLE_DEGRADED"
            except Exception:
                result["ai_status"] = "AI_UNAVAILABLE_DEGRADED"

        # Determine adjudication_result
        if ai_label == "unrelated" and effective_score >= 0.80:
            # Mandatory human review: high-confidence candidate classified unrelated
            result["adjudication_result"] = "ESCALATE_TO_OPERATOR"
        elif ai_label in ("exact_api_class", "related_api_class") and effective_score < promote_threshold:
            # AI-confirmed relevant but below threshold: surface dead-zone to Tier 3
            result["adjudication_result"] = "ESCALATE_TO_OPERATOR"
        elif effective_score >= promote_threshold:
            result["adjudication_result"] = "PROMOTE_WITH_JUSTIFICATION"
        elif effective_score >= 0.60:
            result["adjudication_result"] = "ESCALATE_TO_OPERATOR"
        else:
            result["adjudication_result"] = "REJECT"

        results.append(result)
    return results


def adjudicate_review_required(
    candidate_graph: dict,
    authority: Optional[dict],
    *,
    dry_run: bool = True,
    max_candidates: int = 0,
    promote_threshold: float = 0.70,
) -> dict:
    """
    Process REVIEW_REQUIRED candidates through three-tier adjudication.

    Pure business logic — no I/O.
    Returns: {adjudicated, escalated, rejected, tier_stats}
    """
    # Collect REVIEW_REQUIRED candidates
    all_rr = [
        c for c in candidate_graph.get("candidates", [])
        if c.get("decision") == "REVIEW_REQUIRED"
    ]
    total_rr_count = len(all_rr)
    rr_candidates = all_rr[:max_candidates] if max_candidates > 0 else all_rr

    tier1_resolved = []
    tier2_inputs = []

    # Tier 1: deterministic resolution
    for c in rr_candidates:
        source_key = c.get("source_key", "")
        # Check if authority already has an approved record (tier 1 win)
        if authority:
            auth_records = authority.get("authority", {})
            for path, rec in auth_records.items():
                if rec.get("source_key") == source_key and rec.get("allowed_for_generation"):
                    tier1_resolved.append({
                        "source_key": source_key,
                        "target_path": c.get("target_path", ""),
                        "tier": 1,
                        "adjudication_result": "ALREADY_AUTO_APPROVED",
                    })
                    break
            else:
                tier2_inputs.append(c)
        else:
            tier2_inputs.append(c)

    # Tier 2: AI-assisted
    tier2_results = _tier2_ai_adjudicate(
        tier2_inputs, dry_run=dry_run, promote_threshold=promote_threshold,
    )

    promoted = [r for r in tier2_results if r["adjudication_result"] in (
        "PROMOTE_AUTO_APPROVE", "PROMOTE_PLATFORM_CANONICAL", "PROMOTE_WITH_JUSTIFICATION"
    )]
    escalated = [r for r in tier2_results if r["adjudication_result"] == "ESCALATE_TO_OPERATOR"]
    rejected = [r for r in tier2_results if r["adjudication_result"] == "REJECT"]

    return {
        "total_review_required": total_rr_count,
        "tier1_already_approved": len(tier1_resolved),
        "tier2_processed": len(tier2_inputs),
        "promoted": promoted,
        "escalated": escalated,
        "rejected": rejected,
        "tier_stats": {
            "tier1_count": len(tier1_resolved),
            "tier2_promoted": len(promoted),
            "tier2_escalated": len(escalated),
            "tier2_rejected": len(rejected),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Three-tier adjudication for REVIEW_REQUIRED backlink candidates"
    )
    parser.add_argument("--candidate-graph", default=str(CANDIDATE_GRAPH_PATH))
    parser.add_argument("--authority", default=str(AUTHORITY_PATH))
    parser.add_argument("--output-dir", default=str(ADJUDICATION_REPORT_PATH))
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Report without writing authority changes")
    parser.add_argument("--write", action="store_true", default=False,
                        help="Promote qualifying RR records to AUTO_APPROVE_EXACT in authority")
    parser.add_argument("--max-candidates", type=int, default=0,
                        help="Max candidates to process (0 = unlimited, default: 0)")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="Minimum final_score for Tier 2 promotion (default: 0.70)")
    args = parser.parse_args()

    if args.write and args.dry_run:
        print("ERROR: --write and --dry-run are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    # Default to dry-run if neither flag is set
    if not args.write:
        args.dry_run = True

    graph_path = Path(args.candidate_graph)
    if not graph_path.exists():
        print(f"ERROR: candidate_graph.json not found at {graph_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading candidate graph from {graph_path} ...")
    candidate_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(candidate_graph, dict):
        print("ERROR: Candidate graph must be a JSON object", file=sys.stderr)
        sys.exit(1)

    authority: Optional[dict] = None
    auth_path = Path(args.authority)
    if auth_path.exists():
        authority = json.loads(auth_path.read_text(encoding="utf-8"))
        if not isinstance(authority, dict):
            print("ERROR: Authority file must be a JSON object", file=sys.stderr)
            sys.exit(1)
        print(f"Loaded authority from {auth_path}")

    rr_count = sum(1 for c in candidate_graph.get("candidates", [])
                   if c.get("decision") == "REVIEW_REQUIRED")
    print(f"REVIEW_REQUIRED candidates: {rr_count}")

    result = adjudicate_review_required(
        candidate_graph,
        authority,
        dry_run=args.dry_run,
        max_candidates=args.max_candidates,
        promote_threshold=args.threshold,
    )

    stats = result["tier_stats"]
    print(f"Tier 1 (already approved): {stats['tier1_count']}")
    print(f"Tier 2 promoted: {stats['tier2_promoted']}")
    print(f"Tier 2 escalated (-> Tier 3): {stats['tier2_escalated']}")
    print(f"Tier 2 rejected: {stats['tier2_rejected']}")

    if args.write and not args.dry_run:
        # Promotion write path
        promoted = result["promoted"]
        if not promoted:
            print("No records to promote. Nothing to write.")
        elif authority is None:
            print("ERROR: --write requires an existing authority file", file=sys.stderr)
            sys.exit(1)
        else:
            # Load anchor registry
            anchor_registry = None
            try:
                anchor_registry = load_anchor_registry()
                print("Anchor text registry loaded.")
            except FileNotFoundError:
                print("WARNING: anchor_text_registry.yaml not found — anchors will use fallback.")

            families_map = _load_families_map()
            platforms_map = _load_platforms_map()

            promo_result = promote_to_authority(
                promoted,
                candidate_graph,
                authority,
                anchor_registry=anchor_registry,
                families_map=families_map,
                platforms_map=platforms_map,
            )

            print(f"Promoted: {promo_result['promoted_count']}")
            print(f"Skipped: {promo_result['skipped_count']}")
            if promo_result["errors"]:
                for err in promo_result["errors"]:
                    print(f"  ERROR: {err}", file=sys.stderr)

            # Write updated authority
            authority["generated_at"] = datetime.now(timezone.utc).isoformat()
            auth_path.write_text(
                json.dumps(authority, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Authority updated: {auth_path}")
            print(f"Total authority records: {len(authority.get('authority', {}))}")
    else:
        # Dry-run report
        print("Dry-run: no authority records written.")
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "tier2_results.md"
        lines = [
            "# Tier 2 Adjudication Results\n",
            f"Generated: {result['generated_at']}\n",
            f"Total REVIEW_REQUIRED: {result['total_review_required']}\n\n",
            f"| Metric | Count |\n|--------|-------|\n",
            f"| Tier 1 already approved | {stats['tier1_count']} |\n",
            f"| Tier 2 promoted | {stats['tier2_promoted']} |\n",
            f"| Tier 2 escalated to Tier 3 | {stats['tier2_escalated']} |\n",
            f"| Tier 2 rejected | {stats['tier2_rejected']} |\n\n",
        ]
        if result["escalated"]:
            lines.append("## Operator Escalations\n\n")
            for e in result["escalated"][:10]:
                lines.append(f"- `{e['source_key']}` → `{e['target_path']}`\n")
        report_path.write_text("".join(lines), encoding="utf-8")
        print(f"Report written: {report_path}")


if __name__ == "__main__":
    main()
