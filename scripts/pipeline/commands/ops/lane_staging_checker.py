"""lane_staging_checker.py — Exact-path staging checker (TC-LCM-05).

Compares staged files (git diff --cached --name-only) against a lane manifest's
owned_path_prefixes.  Rejects broad-wildcard staging and unowned staged files.

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_staging_checker.py --manifest path/to/LANE-A.json
  python scripts/pipeline/commands/ops/lane_staging_checker.py --manifest LANE-A.json --stdin
  python scripts/pipeline/commands/ops/lane_staging_checker.py --manifest LANE-A.json --format json

Exit codes:
  0  All staged files within lane scope (PASS)
  1  Out-of-scope or unowned staged files detected (FAIL)
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


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Manifest root must be a JSON object: {path}")
    return data


def get_staged_files() -> list[str]:
    """Return list of staged files (git diff --cached --name-only)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_owned(filepath: str, owned_prefixes: list[str]) -> bool:
    norm = filepath.replace("\\", "/")
    for prefix in owned_prefixes:
        norm_prefix = prefix.replace("\\", "/")
        if not norm_prefix.endswith("/"):
            norm_prefix += "/"
        if norm.startswith(norm_prefix) or norm == norm_prefix.rstrip("/"):
            return True
    return False


def check_staged(staged_files: list[str], manifest: dict) -> dict:
    """Check staged files against manifest owned_path_prefixes.

    Returns result dict with: staged, owned, unowned, overall (PASS/FAIL), summary.
    """
    owned_prefixes: list[str] = manifest.get("owned_path_prefixes", [])
    lane_id: str = manifest.get("lane_id", "<unknown>")

    owned: list[str] = []
    unowned: list[str] = []

    for f in staged_files:
        if is_owned(f, owned_prefixes):
            owned.append(f)
        else:
            unowned.append(f)

    overall = "PASS" if not unowned else "FAIL"
    return {
        "lane_id": lane_id,
        "staged_count": len(staged_files),
        "owned": owned,
        "unowned": unowned,
        "overall": overall,
        "summary": (
            f"PASS: {len(owned)} staged file(s) all within lane scope"
            if overall == "PASS"
            else f"FAIL: {len(unowned)} staged file(s) outside lane scope"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exact-path staging checker (TC-LCM-05)."
    )
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Lane manifest JSON file")
    parser.add_argument("--stdin", action="store_true",
                        help="Read newline-delimited staged file list from stdin")
    parser.add_argument("--format", choices=["json", "table"], default="table")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        if args.stdin:
            staged = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
        else:
            staged = get_staged_files()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git diff --cached failed: {e}", file=sys.stderr)
        return 2

    result = check_staged(staged, manifest)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Lane: {result['lane_id']}")
        print(f"Staged: {result['staged_count']}")
        if result["unowned"]:
            print(f"UNOWNED STAGED FILES ({len(result['unowned'])}):")
            for f in result["unowned"]:
                print(f"  - {f}")
        print(f"\n{result['summary']}")

    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
