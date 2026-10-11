"""content_enrich.py — CLI entry point for S-98 content enrichment.

Usage:
    python scripts/pipeline/commands/enrichment/content_enrich.py font python --mode audit
    python scripts/pipeline/commands/enrichment/content_enrich.py font python --mode plan
    python scripts/pipeline/commands/enrichment/content_enrich.py font python --mode dry-run
    python scripts/pipeline/commands/enrichment/content_enrich.py font python --mode execute --allow-local-content-write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve repo paths
_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _SCRIPT_DIR.parent.parent  # commands/enrichment/ -> commands/ -> pipeline/
_LIB_DIR = str(_PIPELINE_DIR / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_REPO_ROOT = _PIPELINE_DIR.parent.parent  # pipeline/ -> scripts/ -> repo root
_REPORTS_ROOT = _REPO_ROOT / "reports" / "enrichment"

from enrichment.coverage_matrix import build_coverage_matrix, matrix_to_markdown, configure as configure_matrix  # noqa: E402
from enrichment.taxonomy import CoverageStatus, SUBDOMAINS  # noqa: E402


VALID_MODES = ("audit", "plan", "dry-run", "execute")


def _ensure_output_dir(family: str, platform: str) -> Path:
    out = _REPORTS_ROOT / family / platform
    out.mkdir(parents=True, exist_ok=True)
    return out


def run_audit(family: str, platform: str) -> dict:
    """Run coverage audit: build matrix, write outputs."""
    result = build_coverage_matrix(family, platform)
    if "error" in result:
        print(f"AUDIT ERROR: {result['error']}", file=sys.stderr)
        return result

    out_dir = _ensure_output_dir(family, platform)

    # Write JSON
    json_path = out_dir / "coverage-matrix.json"
    json_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    # Write markdown
    md_path = out_dir / "coverage-matrix.md"
    md_path.write_text(matrix_to_markdown(result), encoding="utf-8")

    # Write audit summary
    summary = _build_audit_summary(result)
    summary_path = out_dir / "audit-summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"Audit complete for {family}/{platform}")
    print(f"  Clusters: {result['cluster_count']}")
    print(f"  Coverage ratio: {result['summary']['coverage_ratio']:.1%}")
    print(f"  Uncovered cells: {result['summary']['uncovered']}")
    print(f"  Output: {out_dir}")

    return result


def _build_audit_summary(result: dict) -> str:
    """Build human-readable audit summary markdown."""
    lines = [
        f"# Enrichment Audit Summary: {result['family']}/{result['platform']}",
        "",
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "## Key Metrics",
        "",
        f"- Clusters: {result['cluster_count']}",
        f"- Total claims: {result['total_claims']}",
        f"- Coverage ratio: {result['summary']['coverage_ratio']:.1%}",
        f"- Uncovered cells: {result['summary']['uncovered']} / {result['summary']['total_cells']}",
        "",
        "## Gap Analysis",
        "",
    ]

    matrix = result["matrix"]
    for cluster in result["clusters"]:
        cat = cluster["category"]
        row = matrix.get(cat, {})
        gaps = [sd for sd in SUBDOMAINS if row.get(sd) == CoverageStatus.UNCOVERED.value]
        if gaps:
            short = {
                "products.aspose.org": "Products",
                "docs.aspose.org": "Docs",
                "kb.aspose.org": "KB",
                "blog.aspose.org": "Blog",
                "reference.aspose.org": "Reference",
            }
            gap_names = ", ".join(short.get(g, g) for g in gaps)
            lines.append(f"- **{cat}** ({cluster['claim_count']} claims): uncovered in {gap_names}")

    lines.append("")
    lines.append("## Content File Counts")
    lines.append("")
    for sd, count in result.get("content_file_counts", {}).items():
        lines.append(f"- {sd}: {count} files")

    lines.append("")
    lines.append("## Knowledge Availability")
    lines.append("")
    for artifact, available in result.get("knowledge_available", {}).items():
        status = "available" if available else "missing"
        lines.append(f"- {artifact}: {status}")

    lines.append("")
    return "\n".join(lines)


def run_plan(family: str, platform: str, *, dry_run: bool = False) -> dict:
    """Run candidate generation (plan/dry-run mode)."""
    # Import here to avoid circular dependency during audit-only usage
    from enrichment.candidate_generator import generate_candidates, validate_denominator

    audit_result = run_audit(family, platform)
    if "error" in audit_result:
        return audit_result

    candidates = generate_candidates(audit_result)
    denominator_check = validate_denominator(candidates)

    out_dir = _ensure_output_dir(family, platform)

    # Write candidate list
    candidate_path = out_dir / "candidate-list.json"
    candidate_path.write_text(
        json.dumps(candidates, indent=2, default=str),
        encoding="utf-8",
    )

    # Write denominator check
    denom_path = out_dir / "denominator-check.json"
    denom_path.write_text(
        json.dumps(denominator_check, indent=2),
        encoding="utf-8",
    )

    if not denominator_check["valid"]:
        print(f"DENOMINATOR INVARIANT FAILED: {denominator_check}", file=sys.stderr)
        return {"error": "denominator_invariant_failed", "details": denominator_check}

    # Build decisions
    from enrichment.candidate_generator import build_decisions
    decisions = build_decisions(candidates, audit_result)

    decisions_path = out_dir / "enrichment-decisions.json"
    decisions_path.write_text(
        json.dumps(decisions, indent=2, default=str),
        encoding="utf-8",
    )

    # Build handoff manifest
    from enrichment.candidate_generator import build_handoff_manifest
    manifest = build_handoff_manifest(decisions, family, platform, dry_run=dry_run)

    manifest_path = out_dir / "handoff-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )

    mode_label = "dry-run" if dry_run else "plan"
    print(f"{mode_label.title()} complete for {family}/{platform}")
    print(f"  Candidates: {len(candidates['candidates'])}")
    print(f"  Denominator valid: {denominator_check['valid']}")
    print(f"  Output: {out_dir}")

    return {
        "audit": audit_result,
        "candidates": candidates,
        "denominator_check": denominator_check,
        "decisions": decisions,
        "manifest": manifest,
        "mode": mode_label,
    }


def run_execute(family: str, platform: str) -> dict:
    """Run controlled local execute mode. Requires --allow-local-content-write."""
    print("Execute mode: generating content locally (no publish/deploy)")
    plan_result = run_plan(family, platform, dry_run=False)
    if "error" in plan_result:
        return plan_result

    from enrichment.executor import execute_plan
    exec_result = execute_plan(plan_result, family, platform)
    return exec_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="S-98 content-enrich: Post-launch content enrichment system"
    )
    parser.add_argument("family", help="Product family (e.g., font)")
    parser.add_argument("platform", help="Platform (e.g., python)")
    parser.add_argument(
        "--mode", choices=VALID_MODES, default="audit",
        help="Operation mode: audit (read-only), plan (candidates), dry-run (plan without write), execute (local generation)"
    )
    parser.add_argument(
        "--allow-local-content-write", action="store_true",
        help="Required flag for execute mode"
    )
    parser.add_argument(
        "--repo-root", default=None,
        help="Override repo root (for testing)"
    )
    args = parser.parse_args()

    if args.repo_root:
        configure_matrix(repo_root=args.repo_root)

    if args.mode == "execute" and not args.allow_local_content_write:
        print("ERROR: Execute mode requires --allow-local-content-write flag", file=sys.stderr)
        sys.exit(1)

    if args.mode == "audit":
        result = run_audit(args.family, args.platform)
    elif args.mode in ("plan", "dry-run"):
        result = run_plan(args.family, args.platform, dry_run=(args.mode == "dry-run"))
    elif args.mode == "execute":
        result = run_execute(args.family, args.platform)
    else:
        print(f"ERROR: Unknown mode: {args.mode}", file=sys.stderr)
        sys.exit(1)

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
