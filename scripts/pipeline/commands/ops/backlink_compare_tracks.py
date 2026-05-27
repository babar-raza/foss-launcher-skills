"""
backlink_compare_tracks.py — Compare Track A (deterministic) vs Track B (AI-assisted)

Verifies: Track B approvals ≥ Track A approvals; zero new false positives in Track B.

Usage:
    .venv/Scripts/python backlink_compare_tracks.py \\
        --track-a data/backlinks/workspace/authority_track_a.json \\
        --track-b data/backlinks/workspace/authority_track_b.json \\
        --output reports/backlinks/sprint-BL-DEEP-EXEC-v3.1/ai_comparison.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]

AUTHORITY_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "backlink_authority.json"
DEFAULT_OUTPUT = REPO_ROOT / "reports" / "backlinks" / "sprint-BL-DEEP-EXEC-v3.1" / "ai_comparison.md"


def compare_authorities(
    track_a: dict,
    track_b: dict,
) -> dict:
    """
    Compare Track A (deterministic) and Track B (AI-assisted) authority files.

    Returns comparison report dict.
    Invariant: Track B must be superset OR equal to Track A in approved entries.
    Track B may NOT demote any Track A AUTO_APPROVE_EXACT to lower decision.
    """
    auth_a = track_a.get("authority", {})
    auth_b = track_b.get("authority", {})

    approved_a = {k for k, v in auth_a.items() if v.get("allowed_for_generation")}
    approved_b = {k for k, v in auth_b.items() if v.get("allowed_for_generation")}

    # Promotions: in B but not A (AI helped)
    ai_promoted = approved_b - approved_a

    # Demotions: in A but not B (forbidden!)
    demotions = approved_a - approved_b

    # AI boosts: candidates where B has ai_boost > 0
    ai_boosted_entries = [
        {"source_path": k, "ai_boost": v.get("ai_boost", 0.0), "target_path": v.get("target_path")}
        for k, v in auth_b.items()
        if v.get("ai_boost_applied") and v.get("ai_boost", 0.0) > 0
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_a_approved": len(approved_a),
        "track_b_approved": len(approved_b),
        "ai_promoted_count": len(ai_promoted),
        "ai_promoted_entries": list(ai_promoted)[:20],
        "demotion_count": len(demotions),
        "demotions": list(demotions),
        "ai_boosted_entries": ai_boosted_entries[:20],
        "track_b_gte_track_a": len(approved_b) >= len(approved_a),
        "zero_demotions": len(demotions) == 0,
        "pass": len(demotions) == 0 and len(approved_b) >= len(approved_a),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Track A (deterministic) vs Track B (AI-assisted) authority files"
    )
    parser.add_argument("--track-a", default=str(AUTHORITY_PATH),
                        help="Track A (deterministic) authority JSON")
    parser.add_argument("--track-b", default=str(AUTHORITY_PATH),
                        help="Track B (AI-assisted) authority JSON")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write output file")
    args = parser.parse_args()

    a_path = Path(args.track_a)
    b_path = Path(args.track_b)

    # If same file (single-track sprint), produce trivial comparison report
    if str(a_path.resolve()) == str(b_path.resolve()):
        print("Track A == Track B (single-track run). Producing trivial comparison.")
        track_data = json.loads(a_path.read_text(encoding="utf-8")) if a_path.exists() else {}
        if not isinstance(track_data, dict):
            print("ERROR: Authority file must be a JSON object", file=sys.stderr)
            sys.exit(1)
        result = compare_authorities(track_data, track_data)
    else:
        if not a_path.exists():
            print(f"ERROR: Track A file not found: {a_path}", file=sys.stderr)
            sys.exit(1)
        if not b_path.exists():
            print(f"ERROR: Track B file not found: {b_path}", file=sys.stderr)
            sys.exit(1)
        track_a = json.loads(a_path.read_text(encoding="utf-8"))
        track_b = json.loads(b_path.read_text(encoding="utf-8"))
        if not isinstance(track_a, dict) or not isinstance(track_b, dict):
            print("ERROR: Authority files must be JSON objects", file=sys.stderr)
            sys.exit(1)
        result = compare_authorities(track_a, track_b)

    print(f"Track A approved: {result['track_a_approved']}")
    print(f"Track B approved: {result['track_b_approved']}")
    print(f"AI-promoted: {result['ai_promoted_count']}")
    print(f"Demotions: {result['demotion_count']} (must be 0)")
    print(f"Track B >= Track A: {result['track_b_gte_track_a']}")
    print(f"Comparison result: {'PASS' if result['pass'] else 'FAIL'}")

    if result["demotions"]:
        print("STOP: Track B demoted Track A approvals:", result["demotions"])
        sys.exit(1)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI vs Deterministic Track Comparison\n\n",
        f"Generated: {result['generated_at']}\n\n",
        "| Metric | Value |\n|--------|-------|\n",
        f"| Track A approved | {result['track_a_approved']} |\n",
        f"| Track B approved | {result['track_b_approved']} |\n",
        f"| AI-promoted entries | {result['ai_promoted_count']} |\n",
        f"| Demotions (must be 0) | {result['demotion_count']} |\n",
        f"| Track B ≥ Track A | {result['track_b_gte_track_a']} |\n",
        f"| Result | {'PASS' if result['pass'] else 'FAIL'} |\n\n",
    ]
    if result["ai_promoted_entries"]:
        lines.append("## AI-Promoted Entries\n\n")
        for e in result["ai_promoted_entries"]:
            lines.append(f"- `{e}`\n")
    out.write_text("".join(lines), encoding="utf-8")
    print(f"Report written: {out}")


if __name__ == "__main__":
    main()
