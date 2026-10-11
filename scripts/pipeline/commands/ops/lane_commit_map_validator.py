"""lane_commit_map_validator.py — Lane commit map validator (TC-LCM-DEFERRED-01).

Verifies that commit SHAs recorded in lane manifests appear in git log ancestry,
producing a commit map report for audit.

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_commit_map_validator.py --lanes-dir path/to/lanes/
  python scripts/pipeline/commands/ops/lane_commit_map_validator.py --manifest LANE-A.json
  python scripts/pipeline/commands/ops/lane_commit_map_validator.py --lanes-dir . --format json

Exit codes:
  0  All claimed SHAs verified in git history (PASS)
  1  One or more SHAs missing from git history, or manifest has no SHA (WARN/FAIL)
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


def load_manifests(paths: list[Path]) -> list[dict]:
    manifests: list[dict] = []
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["_source_file"] = str(p)
            manifests.append(data)
    return manifests


def load_manifests_from_dir(d: Path) -> list[dict]:
    if not d.is_dir():
        raise FileNotFoundError(f"Directory not found: {d}")
    return load_manifests(sorted(d.glob("*.json")))


def git_commit_exists(sha: str) -> bool:
    """Return True if SHA resolves to a commit object in git."""
    if not sha or len(sha) < 7:
        return False
    try:
        r = subprocess.run(
            ["git", "cat-file", "-t", sha],
            capture_output=True, text=True,
        )
        return r.returncode == 0 and r.stdout.strip() == "commit"
    except OSError:
        return False


def git_is_ancestor(ancestor: str, descendant: str) -> bool:
    """Return True if ancestor is an ancestor of descendant in git history."""
    try:
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
        )
        return r.returncode == 0
    except OSError:
        return False


def build_commit_map(manifests: list[dict], *, check_ancestry: bool = False) -> dict:
    """Build commit map from manifests.

    Returns: {entries, summary, overall}
    """
    entries: list[dict] = []
    missing_sha: list[str] = []
    not_in_git: list[str] = []
    ancestry_fails: list[str] = []

    for m in manifests:
        lane_id = m.get("lane_id", "<unknown>")
        commit_sha = m.get("commit_sha")
        status = m.get("status", "UNKNOWN")

        if not commit_sha:
            entries.append({
                "lane_id": lane_id,
                "commit_sha": None,
                "status": status,
                "verified": False,
                "note": "No commit_sha in manifest",
            })
            if status in ("COMMITTED", "INTEGRATION_VERIFIED", "VERIFIED"):
                missing_sha.append(lane_id)
            continue

        in_git = git_commit_exists(commit_sha)
        ancestry_ok: bool | None = None
        if in_git and check_ancestry:
            ancestry_ok = git_is_ancestor(commit_sha, "HEAD")
            if not ancestry_ok:
                ancestry_fails.append(f"{lane_id}:{commit_sha[:8]}")

        if not in_git:
            not_in_git.append(f"{lane_id}:{commit_sha[:8]}")

        entries.append({
            "lane_id": lane_id,
            "commit_sha": commit_sha,
            "status": status,
            "verified": in_git,
            "ancestry_ok": ancestry_ok,
            "note": (
                "SHA verified in git"
                if in_git
                else f"SHA {commit_sha[:8]!r} NOT found in git history"
            ),
        })

    if not_in_git or missing_sha:
        overall = "FAIL"
    elif ancestry_fails:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "entries": entries,
        "overall": overall,
        "total": len(manifests),
        "verified_count": sum(1 for e in entries if e.get("verified")),
        "missing_sha": missing_sha,
        "not_in_git": not_in_git,
        "ancestry_fails": ancestry_fails,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lane commit map validator (TC-LCM-DEFERRED-01)."
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--lanes-dir", type=Path,
                   help="Directory of lane manifest JSON files")
    parser.add_argument("--manifest", type=Path, action="append", dest="manifests",
                        help="Individual manifest file (repeatable)")
    parser.add_argument("--check-ancestry", action="store_true",
                        help="Also verify each SHA is an ancestor of HEAD")
    parser.add_argument("--format", choices=["json", "table"], default="table")
    args = parser.parse_args(argv)

    all_manifests: list[dict] = []
    try:
        if args.lanes_dir:
            all_manifests.extend(load_manifests_from_dir(args.lanes_dir))
        if args.manifests:
            all_manifests.extend(load_manifests(args.manifests))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not all_manifests:
        print("ERROR: No manifests found.", file=sys.stderr)
        return 2

    result = build_commit_map(all_manifests, check_ancestry=args.check_ancestry)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Commit map — {result['total']} lane(s), "
              f"{result['verified_count']} SHA(s) verified")
        print()
        for e in result["entries"]:
            sha_disp = e["commit_sha"][:8] if e["commit_sha"] else "NONE"
            marker = "PASS" if e.get("verified") else "FAIL"
            print(f"  [{marker}] {e['lane_id']}: {sha_disp} — {e['note']}")
        if result["missing_sha"]:
            print(f"\nWARN: Committed lanes with no SHA: {result['missing_sha']}")
        if result["not_in_git"]:
            print(f"\nFAIL: SHAs not in git: {result['not_in_git']}")
        print(f"\nOverall: {result['overall']}")

    return 0 if result["overall"] in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
