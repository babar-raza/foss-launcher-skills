#!/usr/bin/env python3
# Adapted from aspose.org
"""build_page_depth_inventory.py — Build a depth-aware page type inventory across all in-scope aspose.org content.

Walks all 5 subdomain content roots, classifies each file by the §Q.3 page type
table, and emits JSON + Markdown reports.

Usage:
    python scripts/pipeline/commands/ops/build_page_depth_inventory.py
    python scripts/pipeline/commands/ops/build_page_depth_inventory.py --subdomain docs.aspose.org
    python scripts/pipeline/commands/ops/build_page_depth_inventory.py --family words

Exit codes:
    0   Success — inventory written
    1   Error rate > 1%
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
import os
from typing import Optional

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))
REPO_ROOT = _REPO_ROOT

# ── Locale patterns (§1.2 + §Q.2) ───────────────────────────────────────────

LOCALE_CODES = {
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
}

# Locale suffix in filename: index.de.md, archive.fr.md
# Non-capturing group prevents bare alternation matching substrings
LOCALE_RE = re.compile(r'\.(?:' + '|'.join(LOCALE_CODES) + r')\.md$')

# Known family names (§1.2)
KNOWN_FAMILIES = {
    "3d", "barcode", "cad", "cells", "diagram", "drawing", "email", "finance",
    "font", "gis", "html", "imaging", "medical", "note", "ocr", "omr", "page",
    "pdf", "psd", "pub", "slides", "svg", "tasks", "tex", "words", "zip",
}

# Subdomain content roots
SUBDOMAIN_ROOTS = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class PageRecord:
    file_path: str          # repo-relative
    subdomain: str
    depth: int              # plan-depth: total path segments after content root (dir_count + 1)
    page_type: str          # from §Q.3 table
    family: Optional[str]
    platform: Optional[str]
    layout: Optional[str]   # from frontmatter
    page_role: Optional[str]
    auto_updatable: Optional[bool]
    error: Optional[str]


# ── Frontmatter extraction ────────────────────────────────────────────────────

def read_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter fields: layout, page_role, type, auto_updatable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}

    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    fm_text = text[3:end]
    result: dict = {}

    for line in fm_text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip().strip('"').strip("'")
        if key in ("layout", "page_role", "type"):
            result[key] = val
        elif key == "auto_updatable":
            result["auto_updatable"] = val.lower() not in ("false", "no", "0")

    return result


# ── Page type classification (§Q.3) ─────────────────────────────────────────
#
# Depth semantics used here:
#   dir_count = len(dir_parts) = number of directory segments (NOT including filename)
#   plan_depth = dir_count + 1 (includes filename, matches §Q.2 table)
#
# Mapping (after stripping /en/ root or blog root):
#   {fam}/_index.md              → dir_count=1  (plan depth 1: family index)
#   {fam}/{plat}/_index.md       → dir_count=2  (plan depth 2: platform index)
#   {fam}/{plat}/{cls}.md        → dir_count=2  (plan depth 3: reference class)
#   {fam}/{plat}/{cat}/_index.md → dir_count=3  (plan depth 3: docs toc)
#   {fam}/{plat}/{cat}/{art}.md  → dir_count=3  (plan depth 4: docs article)
#   {fam}/{plat}/{slug}/index.md → dir_count=3  (plan depth 4: blog post)

def classify_page(
    dir_parts: list[str],   # directory segments relative to subdomain content root (no filename)
    filename: str,
    subdomain: str,
    fm: dict,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Returns (page_type, family, platform).
    Uses dir_count = len(dir_parts) for all depth comparisons.
    """
    dc = len(dir_parts)  # dir_count

    family = dir_parts[0] if dc >= 1 and dir_parts[0] in KNOWN_FAMILIES else None
    platform = dir_parts[1] if dc >= 2 else None

    # ── Subdomain root indexes (dc=0, out of scope) ──────────────────────────
    if dc == 0 and filename == "_index.md" and subdomain != "products.aspose.org":
        return "subdomain-root", None, None

    # ── Blog (root = content/blog.aspose.org, no /en/) ──────────────────────
    if subdomain == "blog.aspose.org":
        # Site utility pages at root level (search, etc.)
        if dc == 0:
            return "blog-utility", None, None
        # Archive files at root level
        if re.match(r'^archive', filename):
            return "blog-archive", family, platform
        # blog/{fam}/{plat}/{slug}/index.md → dc=3
        if dc == 3 and filename == "index.md":
            return "blog-post", family, platform
        return "UNKNOWN_PATTERN", family, platform

    # ── Docs (root = content/docs.aspose.org/en) ────────────────────────────
    if subdomain == "docs.aspose.org":
        if dc == 1 and filename == "_index.md":
            return "docs-family-index", family, None
        if dc == 2 and filename == "_index.md":
            return "docs-platform-index", family, platform
        if dc == 3 and filename == "_index.md":
            return "docs-category-toc", family, platform
        # Docs articles: either {fam}/{plat}/{cat}/{art}.md (dc=3) or {fam}/{plat}/{art}.md (dc=2)
        if dc == 3 and filename.endswith(".md"):
            return "docs-article", family, platform
        if dc == 2 and filename.endswith(".md"):
            return "docs-article", family, platform
        return "UNKNOWN_PATTERN", family, platform

    # ── KB (root = content/kb.aspose.org/en) ────────────────────────────────
    if subdomain == "kb.aspose.org":
        if dc == 1 and filename == "_index.md":
            return "kb-family-index", family, None
        if dc == 2 and filename == "_index.md":
            return "kb-platform-index", family, platform
        # kb-article: {fam}/{plat}/{art}.md → dc=2, non-_index
        if dc == 2 and filename.endswith(".md"):
            return "kb-article", family, platform
        return "UNKNOWN_PATTERN", family, platform

    # ── Reference (root = content/reference.aspose.org/en) ──────────────────
    if subdomain == "reference.aspose.org":
        if dc == 1 and filename == "_index.md":
            return "reference-family-index", family, None
        if dc == 2 and filename == "_index.md":
            return "reference-platform-index", family, platform
        # reference-class: {fam}/{plat}/{cls}.md → dc=2, non-_index
        if dc == 2 and filename.endswith(".md"):
            return "reference-class", family, platform
        # reference-nested-class: {fam}/{plat}/{cls}/{nested}.md → dc=3 (9 files)
        if dc == 3 and filename.endswith(".md"):
            return "reference-nested-class", family, platform
        # depth-5+ or other unexpected structure
        return "UNKNOWN_PATTERN", family, platform

    # ── Products (root = content/products.aspose.org/en) ────────────────────
    if subdomain == "products.aspose.org":
        # Site root _index.md (dc=0)
        if dc == 0 and filename == "_index.md":
            return "products-root", None, None
        # products-family: {fam}/_index.md → dc=1
        if dc == 1 and filename == "_index.md":
            layout = fm.get("layout", "")
            if layout == "homepage":
                return "products-root", None, None
            return "products-family", family, None
        # products-plugin: {fam}/{plat}/_index.md → dc=2
        if dc == 2 and filename == "_index.md":
            return "products-plugin", family, platform
        return "UNKNOWN_PATTERN", family, platform

    return "UNKNOWN_PATTERN", None, None


# ── Walk a subdomain ─────────────────────────────────────────────────────────

def walk_subdomain(
    subdomain: str,
    root: Path,
    filter_family: Optional[str] = None,
) -> tuple[list[PageRecord], int]:
    """
    Walk the content root for a subdomain.
    Returns (records, error_count).
    """
    records: list[PageRecord] = []
    errors = 0

    if not root.exists():
        return records, 0

    is_blog = (subdomain == "blog.aspose.org")

    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        parts = list(rel.parts)      # all path parts including filename
        filename = parts[-1]
        dir_parts = parts[:-1]       # directory segments only

        # Skip locale-suffixed files (properly grouped regex)
        if LOCALE_RE.search(filename):
            continue

        # Blog: skip top-level locale directories (35 confirmed locale dirs)
        if is_blog and dir_parts and dir_parts[0] in LOCALE_CODES:
            continue

        # Family filter
        top_dir = dir_parts[0] if dir_parts else None
        if filter_family and top_dir and top_dir != filter_family:
            continue

        # Plan depth = dir_count + 1 (matches §Q.2 table numbering)
        plan_depth = len(dir_parts) + 1

        try:
            fm = read_frontmatter(path)
            page_type, family, platform = classify_page(dir_parts, filename, subdomain, fm)
            records.append(PageRecord(
                file_path=str(path.relative_to(root.parent.parent.parent)),
                subdomain=subdomain,
                depth=plan_depth,
                page_type=page_type,
                family=family,
                platform=platform,
                layout=fm.get("layout"),
                page_role=fm.get("page_role"),
                auto_updatable=fm.get("auto_updatable"),
                error=None,
            ))
        except Exception as exc:
            errors += 1
            records.append(PageRecord(
                file_path=str(path.relative_to(root.parent.parent.parent)),
                subdomain=subdomain,
                depth=plan_depth,
                page_type="ERROR",
                family=None,
                platform=None,
                layout=None,
                page_role=None,
                auto_updatable=None,
                error=str(exc),
            ))

    return records, errors


# ── Report ───────────────────────────────────────────────────────────────────

def generate_markdown_report(all_records: list[PageRecord]) -> str:
    lines = [
        "# Page Type Depth Inventory",
        f"**Total files scanned:** {len(all_records)}",
        "",
        "---",
        "",
    ]

    by_subdomain: dict[str, list[PageRecord]] = defaultdict(list)
    for r in all_records:
        by_subdomain[r.subdomain].append(r)

    lines.append("## Per-Subdomain Summary")
    lines.append("")

    for sd, recs in sorted(by_subdomain.items()):
        lines.append(f"### {sd}")
        lines.append("")
        by_type: dict[str, int] = defaultdict(int)
        by_depth: dict[int, int] = defaultdict(int)
        unknown = []
        errors = []
        for r in recs:
            by_type[r.page_type] += 1
            by_depth[r.depth] += 1
            if r.page_type == "UNKNOWN_PATTERN":
                unknown.append(r.file_path)
            if r.page_type == "ERROR":
                errors.append(f"{r.file_path}: {r.error}")

        lines.append(f"**Total:** {len(recs)}")
        lines.append("")
        lines.append("**By page type:**")
        lines.append("")
        lines.append("| Page Type | Count |")
        lines.append("|-----------|-------|")
        for pt, count in sorted(by_type.items()):
            lines.append(f"| {pt} | {count} |")
        lines.append("")
        lines.append("**By depth:**")
        lines.append("")
        lines.append("| Depth | Count |")
        lines.append("|-------|-------|")
        for d, count in sorted(by_depth.items()):
            lines.append(f"| {d} | {count} |")
        lines.append("")

        if unknown:
            lines.append(f"**UNKNOWN_PATTERN files ({len(unknown)}):**")
            for f in unknown[:20]:
                lines.append(f"- {f}")
            if len(unknown) > 20:
                lines.append(f"- ... and {len(unknown) - 20} more")
            lines.append("")

        if errors:
            lines.append(f"**ERROR files ({len(errors)}):**")
            for e in errors[:10]:
                lines.append(f"- {e}")
            lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build depth-aware page type inventory across all aspose.org content.",
    )
    parser.add_argument(
        "--subdomain", choices=list(SUBDOMAIN_ROOTS.keys()),
        help="Restrict to one subdomain.",
    )
    parser.add_argument(
        "--family", metavar="FAMILY",
        help="Restrict to one family.",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root

    subdomains = [args.subdomain] if args.subdomain else list(SUBDOMAIN_ROOTS.keys())
    all_records: list[PageRecord] = []
    total_errors = 0
    total_files = 0

    for sd in subdomains:
        root = repo_root / SUBDOMAIN_ROOTS[sd]
        print(f"Walking {sd} at {root} ...", file=sys.stderr)
        recs, err_count = walk_subdomain(sd, root, args.family)
        all_records.extend(recs)
        total_errors += err_count
        total_files += len(recs)
        print(f"  -> {len(recs)} files, {err_count} errors", file=sys.stderr)

    # Error rate check
    if total_files > 0:
        error_rate = total_errors / total_files
        if error_rate > 0.01:
            print(f"ERROR: Error rate {error_rate:.1%} > 1% threshold", file=sys.stderr)
            return 1

    # Unknown pattern summary
    unknown_count = sum(1 for r in all_records if r.page_type == "UNKNOWN_PATTERN")
    print(f"\nTotal: {total_files} files, {total_errors} errors, {unknown_count} UNKNOWN_PATTERN", file=sys.stderr)

    # Write JSON
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "page_type_depth_inventory.json"
    json_records = [asdict(r) for r in all_records]
    json_path.write_text(
        json.dumps({"records": json_records, "total": total_files, "errors": total_errors}, indent=2),
        encoding="utf-8",
    )
    print(f"Written: {json_path}", file=sys.stderr)

    # Write Markdown
    md_path = reports_dir / "page_type_depth_inventory.md"
    md_path.write_text(generate_markdown_report(all_records), encoding="utf-8")
    print(f"Written: {md_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
