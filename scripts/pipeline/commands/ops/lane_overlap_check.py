"""lane_overlap_check.py — Detect overlapping lane ownership.

Checks that no two active lanes claim overlapping owned_path_prefixes.

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_overlap_check.py --dir path/to/lanes/
  python scripts/pipeline/commands/ops/lane_overlap_check.py --files lane-a.json lane-b.json

Exit codes:
  0  No overlaps (PASS)
  1  Overlaps detected (FAIL)
  2  I/O or argument error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Statuses that are inactive/terminal and should be excluded from overlap check
INACTIVE_STATUSES = frozenset({
    "REJECTED",
    "REVERTED",
})


def load_manifests(paths: list[Path]) -> list[dict]:
    """Load lane manifests from file paths, filtering out inactive lanes."""
    manifests = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("status") not in INACTIVE_STATUSES:
            manifests.append(data)
    return manifests


def check_overlaps(manifests: list[dict]) -> list[dict]:
    """Check for overlapping owned_path_prefixes between manifests.

    Returns list of conflict dicts: {lane_a, lane_b, prefix_a, prefix_b, type}.
    """
    conflicts: list[dict] = []

    # Check for duplicate lane IDs
    lane_ids = [m.get("lane_id", "<unknown>") for m in manifests]
    seen_ids: dict[str, int] = {}
    for i, lid in enumerate(lane_ids):
        if lid in seen_ids:
            conflicts.append({
                "lane_a": lid,
                "lane_b": lid,
                "prefix_a": "",
                "prefix_b": "",
                "type": "duplicate_lane_id",
            })
        seen_ids[lid] = i

    # Check prefix overlaps between all pairs
    for i in range(len(manifests)):
        for j in range(i + 1, len(manifests)):
            m_a = manifests[i]
            m_b = manifests[j]
            lane_a = m_a.get("lane_id", f"<manifest-{i}>")
            lane_b = m_b.get("lane_id", f"<manifest-{j}>")
            prefixes_a = m_a.get("owned_path_prefixes", [])
            prefixes_b = m_b.get("owned_path_prefixes", [])

            for pa in prefixes_a:
                for pb in prefixes_b:
                    # Normalize: ensure trailing slash for prefix comparison
                    na = pa if pa.endswith("/") else pa + "/"
                    nb = pb if pb.endswith("/") else pb + "/"

                    if na == nb:
                        conflicts.append({
                            "lane_a": lane_a,
                            "lane_b": lane_b,
                            "prefix_a": pa,
                            "prefix_b": pb,
                            "type": "identical",
                        })
                    elif na.startswith(nb):
                        conflicts.append({
                            "lane_a": lane_a,
                            "lane_b": lane_b,
                            "prefix_a": pa,
                            "prefix_b": pb,
                            "type": "nested",
                        })
                    elif nb.startswith(na):
                        conflicts.append({
                            "lane_a": lane_a,
                            "lane_b": lane_b,
                            "prefix_a": pa,
                            "prefix_b": pb,
                            "type": "nested",
                        })

    return conflicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check for overlapping lane ownership."
    )
    parser.add_argument(
        "--dir", type=Path, help="Directory containing lane manifest JSON files"
    )
    parser.add_argument(
        "--files", type=Path, nargs="+", help="Individual lane manifest files"
    )
    args = parser.parse_args(argv)

    if not args.dir and not args.files:
        parser.error("Must specify --dir or --files")

    paths: list[Path] = []
    if args.dir:
        if not args.dir.is_dir():
            print(f"ERROR: Directory not found: {args.dir}", file=sys.stderr)
            return 2
        paths.extend(sorted(args.dir.glob("*.json")))
    if args.files:
        paths.extend(args.files)

    if len(paths) < 2:
        print("PASS: Fewer than 2 manifests — no overlap possible.")
        return 0

    try:
        manifests = load_manifests(paths)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    conflicts = check_overlaps(manifests)

    if conflicts:
        print(f"FAIL: {len(conflicts)} overlap(s) detected:", file=sys.stderr)
        for c in conflicts:
            print(
                f"  {c['type']}: {c['lane_a']} ({c['prefix_a']}) <-> "
                f"{c['lane_b']} ({c['prefix_b']})",
                file=sys.stderr,
            )
        return 1

    print(f"PASS: {len(manifests)} active lane(s), no overlaps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
