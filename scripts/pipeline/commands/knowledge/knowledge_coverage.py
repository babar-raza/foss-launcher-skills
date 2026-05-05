"""knowledge_coverage.py -- Per-claim knowledge coverage report.

Ported/adapted from aspose.org scripts/pipeline/commands/knowledge/knowledge_coverage.py.
Provides read-only coverage analysis: for each claim in the knowledge model,
reports how many content files reference it.

Usage:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/knowledge/knowledge_coverage.py cells java
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/knowledge/knowledge_coverage.py cells java --output-json coverage.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def compute_coverage(family: str, platform: str) -> dict:
    """Compute per-claim coverage across all content files.

    Returns:
        {
            "family": str,
            "platform": str,
            "total_claims": int,
            "covered_claims": int,
            "uncovered_claims": int,
            "coverage_pct": float,
            "claims": {claim_id: {"covered": bool, "file_count": int, "files": [str]}}
        }
    """
    from knowledge_core import Knowledge, discover_content, parse_frontmatter  # noqa

    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        return {
            "family": family,
            "platform": platform,
            "error": f"No knowledge model available for {family}/{platform}",
            "total_claims": 0,
            "covered_claims": 0,
            "uncovered_claims": 0,
            "coverage_pct": 0.0,
            "claims": {},
        }

    claim_ids: list[str] = list(getattr(knowledge, "claim_ids", []) or [])
    claim_coverage: dict[str, dict] = {cid: {"covered": False, "file_count": 0, "files": []} for cid in claim_ids}

    # Scan content files
    content_files = discover_content(family, platform)
    for f in content_files:
        try:
            fm = parse_frontmatter(Path(f))
        except Exception:
            continue
        evidence = fm.get("evidence") or {}
        if not isinstance(evidence, dict):
            continue
        claims = evidence.get("claims", [])
        if not isinstance(claims, list):
            continue
        for cid in claims:
            if isinstance(cid, str) and cid in claim_coverage:
                rec = claim_coverage[cid]
                rec["covered"] = True
                rec["file_count"] += 1
                rec["files"].append(str(f))

    covered = sum(1 for v in claim_coverage.values() if v["covered"])
    total = len(claim_ids)
    pct = round(100.0 * covered / total, 1) if total > 0 else 0.0

    return {
        "family": family,
        "platform": platform,
        "total_claims": total,
        "covered_claims": covered,
        "uncovered_claims": total - covered,
        "coverage_pct": pct,
        "claims": claim_coverage,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="knowledge_coverage",
        description="Per-claim knowledge coverage report.",
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Product platform (e.g. java)")
    parser.add_argument("--output-json", metavar="OUTFILE", dest="output_json",
                        help="Write JSON coverage report to OUTFILE")

    parsed = parser.parse_args(argv)

    report = compute_coverage(parsed.family, parsed.platform)

    print(f"\n=== Knowledge Coverage: {report['family']}/{report['platform']} ===")
    if "error" in report:
        print(f"ERROR: {report['error']}")
    else:
        print(f"Total claims:     {report['total_claims']}")
        print(f"Covered claims:   {report['covered_claims']}")
        print(f"Uncovered claims: {report['uncovered_claims']}")
        print(f"Coverage:         {report['coverage_pct']}%")
    print()

    if parsed.output_json:
        out = Path(parsed.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Report written to {out}")

    sys.exit(0)


if __name__ == "__main__":
    main()
