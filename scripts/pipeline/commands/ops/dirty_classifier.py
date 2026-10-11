"""dirty_classifier.py — Classify dirty working tree files.

Parses `git status --porcelain` output and classifies each dirty file into
categories relevant to the lane-owned commit model.

Usage (CLI):
  python scripts/pipeline/commands/ops/dirty_classifier.py
  python scripts/pipeline/commands/ops/dirty_classifier.py --lanes-dir path/to/lanes/
  python scripts/pipeline/commands/ops/dirty_classifier.py --format json
  python scripts/pipeline/commands/ops/dirty_classifier.py --format summary

Exit codes:
  0  Classification complete (no lane conflicts)
  1  Lane conflicts detected
  2  I/O error
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


# Category classification rules (order matters — first match wins)
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("claude", [".claude/"]),
    ("governance", ["AGENTS.md", "CLAUDE.md", "docs/governance/", "docs/workflows/"]),
    ("layouts", ["layouts/"]),
    ("themes", ["themes/"]),
    ("configs", ["configs/", "config.toml", "config.yaml", "config.yml"]),
    ("scripts", ["scripts/"]),
    ("data", ["data/"]),
    ("knowledge", ["knowledge/"]),
    ("reports", ["reports/"]),
    ("content-blog", ["content/blog.aspose.org/"]),
    ("content-docs", ["content/docs.aspose.org/"]),
    ("content-kb", ["content/kb.aspose.org/"]),
    ("content-products", ["content/products.aspose.org/"]),
    ("content-reference", ["content/reference.aspose.org/"]),
    ("git-hooks", [".git/hooks/"]),
]

# Categories considered forbidden/high-risk for lane-owned modifications
FORBIDDEN_CATEGORIES = frozenset({
    "claude", "governance", "layouts", "themes", "configs", "git-hooks",
})


def classify_path(filepath: str) -> str:
    """Classify a file path into a category."""
    normalized = filepath.replace("\\", "/")
    for category, prefixes in CATEGORY_RULES:
        for prefix in prefixes:
            if normalized.startswith(prefix) or normalized == prefix.rstrip("/"):
                return category
    return "unknown"


def parse_porcelain(lines: list[str]) -> list[dict]:
    """Parse git status --porcelain output into structured records."""
    results = []
    for line in lines:
        if not line or len(line) < 4:
            continue
        index_status = line[0]
        worktree_status = line[1]
        filepath = line[3:].strip()

        # Handle renamed files (old -> new)
        if " -> " in filepath:
            filepath = filepath.split(" -> ")[-1]

        # Remove quotes from paths with special characters
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = filepath[1:-1]

        if index_status == "?" and worktree_status == "?":
            file_type = "untracked"
        elif index_status == "!" and worktree_status == "!":
            file_type = "ignored"
        elif index_status != " " and worktree_status == " ":
            file_type = "staged"
        elif index_status == " " and worktree_status != " ":
            file_type = "modified"
        else:
            file_type = "mixed"

        category = classify_path(filepath)

        results.append({
            "file": filepath,
            "index": index_status,
            "worktree": worktree_status,
            "type": file_type,
            "category": category,
            "forbidden": category in FORBIDDEN_CATEGORIES,
        })
    return results


def check_lane_conflicts(
    classified: list[dict], lane_manifests: list[dict]
) -> list[dict]:
    """Check if any dirty file conflicts with a lane's owned_path_prefixes."""
    conflicts = []
    for item in classified:
        filepath = item["file"]
        for manifest in lane_manifests:
            lane_id = manifest.get("lane_id", "<unknown>")
            for prefix in manifest.get("owned_path_prefixes", []):
                norm_prefix = prefix if prefix.endswith("/") else prefix + "/"
                if filepath.startswith(norm_prefix) or filepath == prefix:
                    conflicts.append({
                        "file": filepath,
                        "category": item["category"],
                        "lane_id": lane_id,
                        "prefix": prefix,
                    })
    return conflicts


def get_git_status() -> list[str]:
    """Run git status --porcelain and return lines."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.splitlines()


def format_summary(classified: list[dict], conflicts: list[dict]) -> str:
    """Format a human-readable summary."""
    lines = [f"Dirty files: {len(classified)}"]

    # Count by category
    cats: dict[str, int] = {}
    for item in classified:
        cats[item["category"]] = cats.get(item["category"], 0) + 1
    for cat in sorted(cats):
        marker = " [FORBIDDEN]" if cat in FORBIDDEN_CATEGORIES else ""
        lines.append(f"  {cat}: {cats[cat]}{marker}")

    # Count by type
    types: dict[str, int] = {}
    for item in classified:
        types[item["type"]] = types.get(item["type"], 0) + 1
    lines.append("")
    lines.append("By status:")
    for t in sorted(types):
        lines.append(f"  {t}: {types[t]}")

    if conflicts:
        lines.append("")
        lines.append(f"LANE CONFLICTS: {len(conflicts)}")
        for c in conflicts:
            lines.append(f"  {c['file']} claimed by {c['lane_id']} ({c['prefix']})")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify dirty working tree files."
    )
    parser.add_argument(
        "--lanes-dir", type=Path,
        help="Directory of lane manifest JSON files for conflict checking"
    )
    parser.add_argument(
        "--format", choices=["json", "summary"], default="summary",
        help="Output format (default: summary)"
    )
    parser.add_argument(
        "--stdin", action="store_true",
        help="Read git status --porcelain output from stdin instead of running git"
    )
    args = parser.parse_args(argv)

    try:
        if args.stdin:
            lines = sys.stdin.read().splitlines()
        else:
            lines = get_git_status()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git status failed: {e}", file=sys.stderr)
        return 2

    classified = parse_porcelain(lines)

    # Load lane manifests for conflict checking
    lane_manifests: list[dict] = []
    if args.lanes_dir and args.lanes_dir.is_dir():
        for f in sorted(args.lanes_dir.glob("*.json")):
            try:
                lane_manifests.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass

    conflicts = check_lane_conflicts(classified, lane_manifests)

    if args.format == "json":
        output = {
            "files": classified,
            "conflicts": conflicts,
            "summary": {
                "total": len(classified),
                "forbidden_count": sum(1 for f in classified if f["forbidden"]),
                "conflict_count": len(conflicts),
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_summary(classified, conflicts))

    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
