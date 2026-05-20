# Adapted from aspose.org
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

try:
    from enrichment.manifest_consumer import (
        build_skill_invocation,
        list_candidates,
        load_handoff_manifest,
        preflight_check,
        select_candidate,
    )
except ImportError:
    def _not_available(*a, **kw):
        raise ImportError("enrichment.manifest_consumer not ported yet")
    build_skill_invocation = list_candidates = load_handoff_manifest = _not_available
    preflight_check = select_candidate = _not_available

try:
    from enrichment.snapshot_guard import take_snapshot
except ImportError:
    take_snapshot = None  # type: ignore[assignment]

try:
    from enrichment.delta_adapter import build_delta, write_delta
except ImportError:
    build_delta = write_delta = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Repo root for run-plan output
# ---------------------------------------------------------------------------
import os as _os
_REPO_ROOT = Path(_os.environ.get("REPO_ROOT", str(_PIPELINE_ROOT.parents[1])))


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
    parser.add_argument("--feature-group", default=None, help="Filter by feature group (update_existing only)")

    parser.add_argument("--list", action="store_true", help="List all candidates and exit")
    parser.add_argument("--dry-run", action="store_true", help="Write run-plan but mark as dry-run")
    parser.add_argument("--snapshot", action="store_true", help="Take pre-write snapshot (update_existing only)")
    parser.add_argument("--build-delta", action="store_true", help="Build knowledge delta adapter output (update_existing only)")

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
            manifest, cluster=args.cluster, index=args.index,
            subdomain=args.subdomain, feature_group=args.feature_group,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Preflight
    pf = preflight_check(candidate, args.family, args.platform)
    invocation = build_skill_invocation(candidate, args.family, args.platform)
    is_update = candidate.get("action", "") == "update_existing_docs_page"

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

    # Snapshot (update_existing only, TC-CE-023)
    snapshot_dir = None
    if args.snapshot and is_update and pf["passed"]:
        target = pf.get("target_exists_at", "")
        if target:
            try:
                snapshot_dir = take_snapshot(
                    args.family, args.platform, [target],
                    trigger="execute_one",
                    candidate_ref=candidate,
                    repo_root=_REPO_ROOT,
                )
                print(f"Snapshot:  {snapshot_dir.relative_to(_REPO_ROOT)}")
            except (ValueError, FileNotFoundError) as exc:
                print(f"Snapshot FAILED: {exc}", file=sys.stderr)
                return 1
        else:
            print("Snapshot skipped: no target_exists_at in preflight", file=sys.stderr)

    # Delta adapter (update_existing only, TC-CE-024)
    delta_path = None
    if args.build_delta and is_update and pf["passed"]:
        delta = build_delta(candidate, args.family, args.platform, repo_root=_REPO_ROOT)
        if "error" not in delta:
            delta_path = write_delta(delta, args.family, args.platform, repo_root=_REPO_ROOT)
            print(f"Delta:     {delta_path.relative_to(_REPO_ROOT)}")
        else:
            print(f"Delta FAILED: {delta.get('error')}: {delta.get('message', '')}", file=sys.stderr)

    # Write run-plan
    plan_path = _write_run_plan(
        candidate, args.family, args.platform, pf, invocation, args.dry_run,
    )
    print(f"Run plan:  {plan_path.relative_to(_REPO_ROOT)}")

    return 0 if pf["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
