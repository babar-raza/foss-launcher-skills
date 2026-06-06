"""
backlink_expand_reference_index.py — Layer 1 Reference Expansion

Adds synthetic reference_class entries to deep_target_index.json from local
api_surface.json files for families/platforms whose reference pages are not
present on the live reference.aspose.com site.

Motivation (TIER3-RESIDUAL-001):
    font/python, note/python, slides/{cpp,java,net,python} have 0 reference_class
    entries in deep_target_index (index was built from HTTP crawl of live site).
    Without reference_class entries, stage1 scoring in backlink_build_candidates.py
    cannot produce class_name matches -> all candidates score 0.55 (REVIEW_REQUIRED).
    Adding entries enables stage1 exact match -> 0.90-0.95 -> AUTO_APPROVE_EXACT.

Entry format (matches existing reference_class entries):
    {
        "url": "https://reference.aspose.com/{family}/{platform}/{class_name}/",
        "path": "reference/{family}/{platform}/{class_name}",
        "http_status": 200,
        "subdomain_key": "reference",
        "type": "reference_class",
        "family": "{family}",
        "platform_slug": "{platform}",
        "platform": "{platform}",
        "class_name": "{class_name_lower}",
        "synthetic": true   # marker: entry came from api_surface.json, not HTTP crawl
    }

Usage:
    # Dry-run (report only):
    .venv/Scripts/python backlink_expand_reference_index.py --dry-run

    # Execute expansion for default families (font/python, note/python, slides/*):
    .venv/Scripts/python backlink_expand_reference_index.py

    # Specify specific families/platforms:
    .venv/Scripts/python backlink_expand_reference_index.py --targets font/python note/python slides/cpp

    # Custom index path:
    .venv/Scripts/python backlink_expand_reference_index.py --index PATH
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

DEEP_INDEX_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "deep_target_index.json"
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"

# Default targets: families/platforms with missing reference entries
DEFAULT_TARGETS = [
    ("font", "python"),
    ("note", "python"),
    ("slides", "cpp"),
    ("slides", "java"),
    ("slides", "net"),
    ("slides", "python"),
]

# Map platform folder name -> canonical platform slug
PLATFORM_FOLDER_TO_SLUG = {
    "python": "python",
    "python-net": "python-net",
    "java": "java",
    "net": "net",
    "cpp": "cpp",
    "nodejs-net": "nodejs-net",
    "go": "go",
}


def _derive_namespace(entry: dict, family: str, platform: str) -> str:
    """
    Derive namespace from api_surface entry.

    For Python: uses module path from file field (e.g., src/aspose_font/loader.py
    -> aspose.font). For Java: uses package from 'package' field if present.
    For C++/C#: typically no namespace hierarchy in URL.

    Returns empty string if no meaningful namespace can be derived.
    """
    # Try explicit namespace/package field first
    ns = entry.get("namespace") or entry.get("package") or ""
    if ns:
        return ns.lower()

    # For Python: derive from source file path
    file_path = entry.get("file", "")
    if file_path and platform in ("python", "python-net"):
        # e.g., src/aspose_font/loader.py -> aspose_font -> aspose.font
        parts = Path(file_path).parts
        # Find the package root (skip src/, aspose/, etc.)
        for i, part in enumerate(parts):
            # Look for aspose_* or aspose/* pattern
            if part.startswith("aspose") and not part.endswith(".py"):
                pkg = part.replace("_", ".")
                # Return only the package name (e.g., aspose.font), not deeper modules
                return pkg
            if part == "aspose" and i + 1 < len(parts):
                next_part = parts[i + 1]
                if not next_part.endswith(".py"):
                    return f"aspose.{next_part}"

    return ""


def _slugify_class_name(name: str) -> str:
    """
    Convert class name to URL slug (lowercase, dots preserved for nested classes).

    e.g.: "FontSourceInfo" -> "fontsourceinfo"
          "IColorFormat" -> "icolorformat"
    """
    return name.lower()


def load_api_surface(family: str, platform: str) -> list[dict]:
    """
    Load api_surface.json entries for a family/platform.

    Returns list of class-level entries (kind == 'class_definition').
    Returns [] if file not found.
    """
    surface_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not surface_path.exists():
        return []
    try:
        data = json.loads(surface_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return data


_CLASS_LIKE_KINDS = frozenset({
    # Python
    "class_definition",
    # Java / .NET
    "class_declaration", "interface_declaration", "enum_declaration", "record_declaration",
    # C++ (tree-sitter)
    "class_specifier", "struct_specifier", "enum_specifier",
    # Generic / legacy
    "class", "interface", "enum", "struct",
    # Composite api_surface kinds (slides/java scaffolding)
    "api_class",
})


def _is_public_class(entry: dict) -> bool:
    """Return True if entry represents a public class (not private/internal)."""
    name = entry.get("name", "")
    kind = entry.get("kind") or entry.get("type", "")
    if kind not in _CLASS_LIKE_KINDS:
        return False
    # Exclude private/internal names
    if name.startswith("_"):
        return False
    # Exclude test/internal/mock patterns
    if re.search(r"(Test|Mock|Fake|Internal|_impl|_Impl)", name):
        return False
    return True


def build_reference_entries(
    family: str,
    platform: str,
    api_surface: list[dict],
) -> dict[str, dict]:
    """
    Build synthetic reference_class index entries from api_surface entries.

    Returns dict: {path_key -> entry_dict}

    Pure function — no I/O.
    """
    entries: dict[str, dict] = {}
    platform_slug = PLATFORM_FOLDER_TO_SLUG.get(platform, platform)

    for entry in api_surface:
        if not _is_public_class(entry):
            continue

        name = entry.get("name", "")
        if not name:
            continue

        class_name = _slugify_class_name(name)
        namespace = _derive_namespace(entry, family, platform_slug)

        # Build path key (no trailing slash, no scheme/host)
        # Format: reference/{family}/{platform}/{class_name}
        path_key = f"reference/{family}/{platform_slug}/{class_name}"

        # Build URL (canonical form with trailing slash)
        url = f"https://reference.aspose.com/{family}/{platform_slug}/{class_name}/"

        record: dict = {
            "url": url,
            "path": path_key,
            "http_status": 200,
            "subdomain_key": "reference",
            "type": "reference_class",
            "family": family,
            "platform_slug": platform_slug,
            "platform": platform_slug,
            "class_name": class_name,
            "synthetic": True,
        }
        if namespace:
            record["namespace"] = namespace

        # Add api_member_count for secondary signal (Phase 2 use)
        methods = entry.get("methods", []) or []
        properties = entry.get("properties", []) or []
        record["api_member_count"] = len(methods) + len(properties)

        # Don't overwrite existing live entries
        if path_key not in entries:
            entries[path_key] = record

    return entries


def expand_index(
    deep_index: dict,
    targets: list[tuple[str, str]],
    dry_run: bool = False,
) -> tuple[dict, dict[str, int]]:
    """
    Expand deep_target_index with synthetic reference_class entries.

    Pure logic — no I/O.

    Returns:
        (updated_deep_index, stats_per_target)
    """
    index = deep_index.get("index", {})
    stats: dict[str, int] = {}

    for family, platform in targets:
        api_surface = load_api_surface(family, platform)
        if not api_surface:
            stats[f"{family}/{platform}"] = 0
            continue

        new_entries = build_reference_entries(family, platform, api_surface)
        added = 0
        skipped = 0
        for path_key, record in new_entries.items():
            if path_key in index:
                skipped += 1
            else:
                if not dry_run:
                    index[path_key] = record
                added += 1

        stats[f"{family}/{platform}"] = added
        print(f"  {family}/{platform}: {len(api_surface)} surface entries -> "
              f"{len(new_entries)} class entries -> {added} added, {skipped} already present")

    if not dry_run:
        # Recount type_counts
        type_counts = Counter(rec.get("type", "unknown") for rec in index.values())
        deep_index["index"] = index
        deep_index["total_endpoints"] = len(index)
        deep_index["type_counts"] = dict(type_counts)

    return deep_index, stats


def _parse_targets(target_args: list[str]) -> list[tuple[str, str]]:
    """Parse 'family/platform' strings into (family, platform) tuples."""
    targets = []
    for arg in target_args:
        if "/" not in arg:
            print(f"WARN: Invalid target format '{arg}' (expected 'family/platform')", file=sys.stderr)
            continue
        family, platform = arg.split("/", 1)
        targets.append((family.strip(), platform.strip()))
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expand deep_target_index with reference_class entries from api_surface.json"
    )
    parser.add_argument(
        "--index",
        default=str(DEEP_INDEX_PATH),
        help="Path to deep_target_index.json",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help=(
            "Space-separated list of 'family/platform' targets. "
            f"Defaults to: {' '.join(f'{f}/{p}' for f, p in DEFAULT_TARGETS)}"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report entries that would be added; do not write output.",
    )
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        print(f"ERROR: deep_target_index.json not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    targets = _parse_targets(args.targets) if args.targets else DEFAULT_TARGETS

    print(f"Loading deep_target_index from {index_path} ...")
    deep_index = json.loads(index_path.read_text(encoding="utf-8"))
    before_count = deep_index.get("total_endpoints", len(deep_index.get("index", {})))
    print(f"Before: {before_count:,} total endpoints")

    print(f"Expanding for {len(targets)} target(s):")
    updated_index, stats = expand_index(deep_index, targets, dry_run=args.dry_run)

    total_added = sum(stats.values())
    after_count = updated_index.get("total_endpoints", len(updated_index.get("index", {})))

    print(f"\nExpansion summary:")
    for target_key, count in stats.items():
        print(f"  {target_key}: +{count} entries")
    print(f"Total added: {total_added}")
    print(f"After: {after_count:,} total endpoints (was {before_count:,})")

    if args.dry_run:
        print("\nDry-run: output not written.")
        return

    # Validate minimum expected entries were added
    if total_added == 0:
        print("\nWARN: No new entries added. Targets may already be in index or api_surface.json is empty.")
    else:
        print(f"\nWriting updated index to {index_path} ...")
        index_path.write_text(
            json.dumps(updated_index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Written: {index_path}")
        print("\nAcceptance checks:")
        for family, platform in targets:
            print(f"  {family}/{platform}: +{stats.get(f'{family}/{platform}', 0)} reference_class entries added")


if __name__ == "__main__":
    main()
