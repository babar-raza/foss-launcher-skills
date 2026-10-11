"""lane_rollback_plan.py — Rollback plan validator (TC-LCM-09).

Uses lane manifests and their commit SHAs plus dependency graph to produce
a safe revert order.  Does NOT perform any actual git revert — output is
a human-readable plan and machine-readable JSON for operator review.

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_rollback_plan.py --lanes-dir path/to/lanes/
  python scripts/pipeline/commands/ops/lane_rollback_plan.py --manifest LANE-A.json --manifest LANE-B.json
  python scripts/pipeline/commands/ops/lane_rollback_plan.py --lanes-dir . --format json

Exit codes:
  0  Rollback plan produced (may include warnings)
  1  Validation errors (missing SHAs, dependency cycles)
  2  I/O error
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import sys as _sys
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PIPELINE_ROOT))


def load_manifests_from_dir(lanes_dir: Path) -> list[dict]:
    """Load all lane manifest JSON files from a directory."""
    if not lanes_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {lanes_dir}")
    manifests = []
    for f in sorted(lanes_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_source_file"] = str(f)
                manifests.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return manifests


def load_manifest_file(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Manifest root must be a JSON object: {path}")
    data["_source_file"] = str(path)
    return data


def topological_sort_reverse(manifests: list[dict]) -> tuple[list[dict], list[str]]:
    """Sort manifests in reverse dependency order (safe revert order).

    Returns (sorted_manifests, error_list).
    Items with no committed SHA are listed last.
    Dependency cycles are reported as errors.
    """
    by_id = {m.get("lane_id", ""): m for m in manifests}
    visited: set[str] = set()
    order: list[str] = []
    errors: list[str] = []

    def visit(lane_id: str, stack: set[str]) -> None:
        if lane_id in visited:
            return
        if lane_id in stack:
            errors.append(f"Dependency cycle detected: {lane_id} in {sorted(stack)}")
            return
        stack.add(lane_id)
        manifest = by_id.get(lane_id)
        if manifest:
            for dep in manifest.get("depends_on_lanes", []):
                if dep in by_id:
                    visit(dep, stack)
        stack.discard(lane_id)
        visited.add(lane_id)
        order.append(lane_id)

    for m in manifests:
        visit(m.get("lane_id", ""), set())

    # Reverse: dependents should be reverted before dependencies
    order.reverse()
    sorted_manifests = [by_id[lid] for lid in order if lid in by_id]
    return sorted_manifests, errors


def verify_sha_in_git(sha: str) -> bool:
    """Return True if SHA exists in git history."""
    if not sha or len(sha) < 7:
        return False
    try:
        result = subprocess.run(
            ["git", "cat-file", "-t", sha],
            capture_output=True, text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "commit"
    except OSError:
        return False


def build_rollback_plan(manifests: list[dict], *, verify_git: bool = False) -> dict:
    """Build rollback plan from a list of manifests.

    Returns dict with: plan_steps, warnings, errors, overall (PASS/WARN/FAIL).
    """
    warnings: list[str] = []
    errors: list[str] = []

    sorted_manifests, sort_errors = topological_sort_reverse(manifests)
    errors.extend(sort_errors)

    plan_steps: list[dict] = []
    for i, m in enumerate(sorted_manifests, start=1):
        lane_id = m.get("lane_id", "<unknown>")
        commit_sha = m.get("commit_sha")
        revert_sha = m.get("revert_sha")
        status = m.get("status", "UNKNOWN")

        sha_verified: bool | None = None
        if verify_git and commit_sha:
            sha_verified = verify_sha_in_git(commit_sha)
            if not sha_verified:
                warnings.append(f"{lane_id}: commit_sha {commit_sha!r} not found in git history")

        if not commit_sha:
            warnings.append(f"{lane_id}: no commit_sha — cannot revert")
            revert_cmd = None
        elif revert_sha:
            revert_cmd = f"git revert {commit_sha}..{revert_sha} --no-commit"
        else:
            revert_cmd = f"git revert {commit_sha} --no-commit"

        plan_steps.append({
            "step": i,
            "lane_id": lane_id,
            "status": status,
            "commit_sha": commit_sha,
            "revert_sha": revert_sha,
            "sha_verified": sha_verified,
            "revert_cmd": revert_cmd,
            "note": (
                f"Revert step {i}: {lane_id}"
                if revert_cmd
                else f"SKIP {lane_id} — no commit SHA"
            ),
        })

    if errors:
        overall = "FAIL"
    elif warnings:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "plan_steps": plan_steps,
        "warnings": warnings,
        "errors": errors,
        "overall": overall,
        "total_lanes": len(manifests),
        "revertable_lanes": sum(1 for s in plan_steps if s["revert_cmd"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rollback plan validator (TC-LCM-09)."
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--lanes-dir", type=Path,
                   help="Directory of lane manifest JSON files")
    parser.add_argument("--manifest", type=Path, action="append", dest="manifests",
                        help="Individual manifest file (repeatable)")
    parser.add_argument("--verify-git", action="store_true",
                        help="Verify commit SHAs exist in git history")
    parser.add_argument("--format", choices=["json", "table"], default="table")
    args = parser.parse_args(argv)

    manifests: list[dict] = []
    try:
        if args.lanes_dir:
            manifests.extend(load_manifests_from_dir(args.lanes_dir))
        if args.manifests:
            for p in args.manifests:
                manifests.append(load_manifest_file(p))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not manifests:
        print("ERROR: No manifests found.", file=sys.stderr)
        return 2

    plan = build_rollback_plan(manifests, verify_git=args.verify_git)

    if args.format == "json":
        print(json.dumps(plan, indent=2))
    else:
        print(f"Rollback plan — {plan['total_lanes']} lane(s), "
              f"{plan['revertable_lanes']} revertable")
        print()
        for step in plan["plan_steps"]:
            print(f"  Step {step['step']}: {step['note']}")
            if step["revert_cmd"]:
                print(f"    cmd: {step['revert_cmd']}")
        if plan["warnings"]:
            print(f"\nWARNINGS ({len(plan['warnings'])}):")
            for w in plan["warnings"]:
                print(f"  ! {w}")
        if plan["errors"]:
            print(f"\nERRORS ({len(plan['errors'])}):")
            for e in plan["errors"]:
                print(f"  ERROR: {e}")
        print(f"\nOverall: {plan['overall']}")

    return 0 if plan["overall"] in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
