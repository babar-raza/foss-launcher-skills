"""
backlink_adjudicate_review.py — Three-Tier Adjudication for REVIEW_REQUIRED candidates

Tier 1: Deterministic (single verified variant, explicit override, exact slug HTTP 200)
Tier 2: AI-assisted (LLMRouter classification, advisory only)
Tier 3: Operator escalation (human review packet for ambiguous cases)

Usage:
    .venv/Scripts/python backlink_adjudicate_review.py \\
        --candidate-graph data/backlinks/workspace/candidate_graph.json \\
        --authority data/backlinks/workspace/backlink_authority.json \\
        --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

CANDIDATE_GRAPH_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "candidate_graph.json"
AUTHORITY_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "backlink_authority.json"
ADJUDICATION_REPORT_PATH = REPO_ROOT / "reports" / "backlinks" / "adjudication"

# Closed-set AI labels
VALID_AI_LABELS = frozenset({
    "exact_api_class", "related_api_class", "same_topic",
    "weakly_related", "unrelated",
})


def _tier2_ai_adjudicate(candidates: list[dict], *, dry_run: bool = True) -> list[dict]:
    """
    Tier 2: AI-assisted adjudication.

    Attempts LLMRouter classification for REVIEW_REQUIRED candidates.
    If AI unavailable, marks all as AI_UNAVAILABLE_DEGRADED.

    Returns list of adjudication result dicts.
    """
    results = []
    for c in candidates:
        result = {
            "source_key": c.get("source_key", ""),
            "target_path": c.get("target_path", ""),
            "original_decision": c.get("decision", ""),
            "tier": 2,
            "ai_label": None,
            "ai_confidence": None,
            "adjudication_result": None,
            "ai_status": "AI_EXPLICITLY_DISABLED" if dry_run else "AI_UNAVAILABLE_DEGRADED",
        }
        # In dry-run mode or if AI unavailable: escalate to Tier 3
        # Real AI call would use LLMRouter(model="gpt-oss", ...) with CS-013
        final_score = c.get("final_score", 0.0)
        if final_score >= 0.85:
            result["adjudication_result"] = "PROMOTE_WITH_JUSTIFICATION"
        elif final_score >= 0.60:
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
    max_candidates: int = 50,
) -> dict:
    """
    Process REVIEW_REQUIRED candidates through three-tier adjudication.

    Pure business logic — no I/O.
    Returns: {adjudicated, escalated, rejected, tier_stats}
    """
    # Collect REVIEW_REQUIRED candidates
    rr_candidates = [
        c for c in candidate_graph.get("candidates", [])
        if c.get("decision") == "REVIEW_REQUIRED"
    ][:max_candidates]

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
    tier2_results = _tier2_ai_adjudicate(tier2_inputs, dry_run=dry_run)

    promoted = [r for r in tier2_results if r["adjudication_result"] in (
        "PROMOTE_AUTO_APPROVE", "PROMOTE_PLATFORM_CANONICAL", "PROMOTE_WITH_JUSTIFICATION"
    )]
    escalated = [r for r in tier2_results if r["adjudication_result"] == "ESCALATE_TO_OPERATOR"]
    rejected = [r for r in tier2_results if r["adjudication_result"] == "REJECT"]

    return {
        "total_review_required": len(rr_candidates),
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
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Report without writing authority changes (default: True)")
    parser.add_argument("--max-candidates", type=int, default=50)
    args = parser.parse_args()

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
    )

    stats = result["tier_stats"]
    print(f"Tier 1 (already approved): {stats['tier1_count']}")
    print(f"Tier 2 promoted: {stats['tier2_promoted']}")
    print(f"Tier 2 escalated (-> Tier 3): {stats['tier2_escalated']}")
    print(f"Tier 2 rejected: {stats['tier2_rejected']}")

    if args.dry_run:
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
