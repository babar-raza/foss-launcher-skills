"""
backlink_merge_candidate_graphs.py

Merges multiple candidate graph JSON files (from different subdomains for the
same family) into a single combined graph suitable for backlink_approve_authority.py.

Usage:
    python backlink_merge_candidate_graphs.py \
        --inputs cg_reference_font.json cg_docs_font.json cg_kb_font.json \
        --output cg_merged_font.json \
        --family font

Why this exists:
    backlink_build_candidates.py --output writes a SINGLE file (overwrites each run).
    To accumulate candidates from multiple subdomains for the same family before
    running approve_authority --merge, those per-subdomain files must be merged here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def merge(input_paths: list[str], output_path: str, family: str) -> dict:
    all_sources: list = []
    all_candidates: list = []
    missing = []

    for p in input_paths:
        fp = Path(p)
        if not fp.exists():
            missing.append(str(p))
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        sources = d.get("sources", [])
        candidates = d.get("candidates", [])
        all_sources.extend(sources)
        all_candidates.extend(candidates)
        subdomain = d.get("subdomain", "?")
        print(f"  + {fp.name}: {len(sources)} sources, {len(candidates)} candidates [{subdomain}]")

    if missing:
        print(f"WARNING: {len(missing)} input files not found (skipped): {missing}", file=sys.stderr)

    decision_counts: dict[str, int] = {}
    for c in all_candidates:
        dec = c.get("decision", "UNKNOWN")
        decision_counts[dec] = decision_counts.get(dec, 0) + 1

    merged = {
        "schema_version": "1.0.0",
        "family": family,
        "platform": None,
        "subdomain": "MULTI_SUBDOMAIN_MERGED",
        "deep_index_hash": "merged",
        "ai_enrichment_used": False,
        "semantic_used": False,
        "stats": {
            "total_candidates": len(all_candidates),
            "total_sources": len(all_sources),
            "decision_counts": decision_counts,
        },
        "sources": all_sources,
        "candidates": all_candidates,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  -> Merged: {len(all_sources)} sources, {len(all_candidates)} candidates -> {output_path}")
    for dec, cnt in sorted(decision_counts.items()):
        print(f"    {dec}: {cnt}")
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge candidate graph JSON files")
    parser.add_argument("--inputs", nargs="+", required=True, help="Input JSON files")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--family", required=True, help="Family name (e.g. font)")
    args = parser.parse_args()
    merge(args.inputs, args.output, args.family)


if __name__ == "__main__":
    main()
