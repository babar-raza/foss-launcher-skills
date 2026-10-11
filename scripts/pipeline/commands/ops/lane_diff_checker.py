"""lane_diff_checker.py — Lane-owned diff checker (TC-LCM-04 + TC-LCM-06).

Compares changed files (from git diff or stdin) against a lane manifest's
owned_path_prefixes.  Rejects out-of-scope files and detects shared/coordinator
file touches (TC-LCM-06).

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_diff_checker.py --manifest path/to/LANE-A.json
  python scripts/pipeline/commands/ops/lane_diff_checker.py --manifest LANE-A.json --base HEAD~1
  python scripts/pipeline/commands/ops/lane_diff_checker.py --manifest LANE-A.json --stdin
  python scripts/pipeline/commands/ops/lane_diff_checker.py --manifest LANE-A.json --format json

Exit codes:
  0  All changed files within lane scope (PASS)
  1  Out-of-scope files or shared-file violations detected (FAIL)
  2  I/O / manifest error
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

# Coordinator/shared file patterns — touching these triggers TC-LCM-06 alert
SHARED_FILE_PATTERNS: list[str] = [
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/",
    "docs/governance/",
    "docs/workflows/",
    "scripts/pipeline/config/registry.yaml",
    "scripts/ci/",
    ".git/hooks/",
    "configs/",
    "layouts/",
    "themes/",
]


def load_manifest(path: Path) -> dict:
    """Load and return a lane manifest dict."""
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Manifest root must be a JSON object: {path}")
    return data


def get_diff_files(base: str | None = None) -> list[str]:
    """Return list of files changed vs base (default: HEAD)."""
    cmd = ["git", "diff", "--name-only"]
    if base:
        cmd.append(base)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_owned(filepath: str, owned_prefixes: list[str]) -> bool:
    """Return True if filepath falls under any owned prefix."""
    norm = filepath.replace("\\", "/")
    for prefix in owned_prefixes:
        norm_prefix = prefix.replace("\\", "/")
        if not norm_prefix.endswith("/"):
            norm_prefix += "/"
        if norm.startswith(norm_prefix) or norm == norm_prefix.rstrip("/"):
            return True
    return False


def is_shared(filepath: str) -> tuple[bool, str]:
    """Return (True, pattern) if filepath matches a shared/coordinator file pattern."""
    norm = filepath.replace("\\", "/")
    for pattern in SHARED_FILE_PATTERNS:
        norm_pattern = pattern.replace("\\", "/")
        if norm.startswith(norm_pattern) or norm == norm_pattern.rstrip("/"):
            return True, pattern
    return False, ""


def check_diff(files: list[str], manifest: dict) -> dict:
    """Check diff files against manifest.

    Returns a result dict with:
      owned, out_of_scope, shared_touches, overall (PASS/FAIL), summary
    """
    owned_prefixes: list[str] = manifest.get("owned_path_prefixes", [])
    shared_prefixes: list[str] = manifest.get("shared_path_prefixes", [])
    lane_id: str = manifest.get("lane_id", "<unknown>")

    owned_files: list[str] = []
    out_of_scope: list[str] = []
    shared_touches: list[dict] = []

    for f in files:
        owned_flag = is_owned(f, owned_prefixes)
        shared_flag, shared_pattern = is_shared(f)

        if shared_flag:
            # Shared-coordinator file touch (TC-LCM-06)
            shared_touches.append({
                "file": f,
                "pattern": shared_pattern,
                "in_shared_prefixes": any(
                    f.replace("\\", "/").startswith(p.replace("\\", "/"))
                    for p in shared_prefixes
                ),
            })
        elif owned_flag:
            owned_files.append(f)
        else:
            out_of_scope.append(f)

    overall = "PASS" if (not out_of_scope and not shared_touches) else "FAIL"
    reasons: list[str] = []
    if out_of_scope:
        reasons.append(f"{len(out_of_scope)} out-of-scope file(s)")
    if shared_touches:
        reasons.append(f"{len(shared_touches)} shared/coordinator file touch(es)")

    return {
        "lane_id": lane_id,
        "total_files": len(files),
        "owned_files": owned_files,
        "out_of_scope": out_of_scope,
        "shared_touches": shared_touches,
        "overall": overall,
        "summary": (
            f"PASS: {len(owned_files)} files owned, 0 violations"
            if overall == "PASS"
            else f"FAIL: {'; '.join(reasons)}"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check lane-owned diff (TC-LCM-04 + TC-LCM-06)."
    )
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Lane manifest JSON file")
    parser.add_argument("--base", default=None,
                        help="Git base ref for diff (default: unstaged changes)")
    parser.add_argument("--stdin", action="store_true",
                        help="Read newline-delimited file list from stdin")
    parser.add_argument("--format", choices=["json", "table"], default="table")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        if args.stdin:
            files = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
        else:
            files = get_diff_files(args.base)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git diff failed: {e}", file=sys.stderr)
        return 2

    result = check_diff(files, manifest)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Lane: {result['lane_id']}")
        print(f"Files checked: {result['total_files']}")
        print(f"Owned: {len(result['owned_files'])}")
        if result["out_of_scope"]:
            print(f"OUT-OF-SCOPE ({len(result['out_of_scope'])}):")
            for f in result["out_of_scope"]:
                print(f"  - {f}")
        if result["shared_touches"]:
            print(f"SHARED TOUCHES ({len(result['shared_touches'])}):")
            for t in result["shared_touches"]:
                print(f"  - {t['file']}  [pattern: {t['pattern']}]")
        print(f"\n{result['summary']}")

    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
