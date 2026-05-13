"""execute_one.py — CLI entry point: select and preflight one enrichment candidate.

Usage:
    python execute_one.py font python --list
    python execute_one.py font python --index 0 --dry-run
    python execute_one.py font python --cluster tables
    python execute_one.py font python --cluster tables --subdomain blog.aspose.org
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap (PIPELINE.md section 2)
# ---------------------------------------------------------------------------
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.manifest_consumer import (
    build_skill_invocation,
    list_candidates,
    load_handoff_manifest,
    preflight_check,
    select_candidate,
)

# ---------------------------------------------------------------------------
# Repo root for run-plan output
# ---------------------------------------------------------------------------
_REPO_ROOT = _PIPELINE_ROOT.parents[1]


def _write_run_plan(
    candidate: dict,
    family: str,
    platform: str,
    preflight: dict,
    invocation: str,
    dry_run: bool,
) -> Path:
    """Write run-plan JSON and return its path."""
    cluster = candidate.get("cluster", "unknown")
    out_dir = _REPO_ROOT / "reports" / "enrichment" / family / platform
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"run-plan-{cluster}.json"

    plan = {
        "family": family,
        "platform": platform,
        "cluster": cluster,
        "candidate": candidate,
        "preflight": preflight,
        "skill_invocation": invocation,
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select and preflight one enrichment candidate.",
    )
    parser.add_argument("family", help="Product family (e.g. font)")
    parser.add_argument("platform", help="Platform (e.g. python)")

    # Selection (mutually informative, not exclusive — cluster+subdomain narrows)
    parser.add_argument("--index", type=int, default=None, help="Select by index")
    parser.add_argument("--cluster", default=None, help="Select by cluster name")
    parser.add_argument("--subdomain", default=None, help="Filter/narrow by subdomain")

    parser.add_argument("--list", action="store_true", help="List all candidates and exit")
    parser.add_argument("--dry-run", action="store_true", help="Write run-plan but mark as dry-run")

    args = parser.parse_args(argv)

    # Load manifest
    try:
        manifest = load_handoff_manifest(args.family, args.platform)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # --list mode
    if args.list:
        print(list_candidates(manifest, subdomain_filter=args.subdomain))
        return 0

    # Selection required
    if args.index is None and args.cluster is None and args.subdomain is None:
        print("ERROR: Provide --index, --cluster, or --subdomain (or --list)", file=sys.stderr)
        return 1

    try:
        candidate = select_candidate(
            manifest, cluster=args.cluster, index=args.index, subdomain=args.subdomain,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Preflight
    pf = preflight_check(candidate, args.family, args.platform)
    invocation = build_skill_invocation(candidate, args.family, args.platform)

    # Display
    print(f"Candidate: cluster={candidate.get('cluster')} "
          f"action={candidate.get('action')} "
          f"subdomain={candidate.get('subdomain')} "
          f"score={candidate.get('score')}")
    print(f"Skill:     {invocation}")
    print(f"Preflight: {'PASS' if pf['passed'] else 'FAIL'}")
    for issue in pf["issues"]:
        print(f"  ISSUE: {issue}")
    for warn in pf["warnings"]:
        print(f"  WARN:  {warn}")

    # Write run-plan
    plan_path = _write_run_plan(
        candidate, args.family, args.platform, pf, invocation, args.dry_run,
    )
    print(f"Run plan:  {plan_path.relative_to(_REPO_ROOT)}")

    return 0 if pf["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
