#!/usr/bin/env python3
"""blog_slug_inventory.py — Scan blog.aspose.org for folder slug quality.

Scans every canonical English index.md in content/blog.aspose.org/**/ and
classifies each folder slug using blog_slug_policy. Produces JSON + Markdown
inventory reports and a repair candidates JSON for MIGRATION_READY slugs only.

Usage:
    python scripts/pipeline/commands/diagnostics/blog_slug_inventory.py \\
        --root content/blog.aspose.org \\
        --out reports/blog-slugs

Output files:
    {out}/blog-folder-slug-inventory.json
    {out}/blog-folder-slug-inventory.md
    {out}/blog-folder-slug-repair-candidates.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow running from repo root or via PYTHONPATH=scripts/pipeline
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

import yaml
from lib.blog_slug_policy import (
    OK, WEAK, BAD_GENERIC, BAD_FALLBACK, BAD_NO_PLATFORM, BAD_TOO_SHORT,
    MIGRATION_READY, NEEDS_REVIEW, BLOCKED_BY_GOVERNANCE,
    classify_folder_slug_quality,
    propose_folder_slug_repair,
    validate_folder_slug,
    build_blog_url_from_index_path,
)

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)

# Depth: content/blog.aspose.org/{family}/{platform}/{slug}/index.md → 4 parts relative
_MIN_DEPTH = 4


def _parse_frontmatter(text: str) -> dict:
    m = _FM_RE.match(text)
    if not m:
        return {}
    try:
        result = yaml.safe_load(m.group(1))
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        return {}


def _is_locale_file(path: Path) -> bool:
    """Return True if the file is a locale translation (e.g. index.ar.md)."""
    stem = path.stem
    # stem for index.ar is "index", but for index.ar.md stem is "index.ar" (no, stem = "index.ar")
    # Actually in Python: Path("index.ar.md").stem == "index.ar", Path("index.ar.md").suffix == ".md"
    # We want to skip files like index.ar.md, index.zh-CN.md
    if stem == "index":
        return False
    # stem like "index.ar" or "index.zh-CN"
    if stem.startswith("index."):
        return True
    return False


def _count_locale_files(folder: Path) -> int:
    return sum(1 for f in folder.glob("index.*.md") if _is_locale_file(f))


def _count_source_file_refs(folder: Path, old_source_file_value: str) -> list[Path]:
    """Find locale files in folder that contain the given source_file value."""
    refs = []
    for f in folder.glob("index.*.md"):
        if not _is_locale_file(f):
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if old_source_file_value in content:
            refs.append(f)
    return refs


def scan_posts(blog_root: Path) -> list[dict]:
    """Scan all English index.md posts under blog_root. Return list of post records."""
    records = []
    for index_md in sorted(blog_root.rglob("index.md")):
        rel = index_md.relative_to(blog_root)
        if len(rel.parts) < _MIN_DEPTH:
            continue
        # Must be exactly: {family}/{platform}/{slug}/index.md
        # rel.parts = (family, platform, slug, 'index.md')
        if len(rel.parts) != _MIN_DEPTH:
            # Deeper nesting not expected; skip
            continue

        family = rel.parts[0]
        platform = rel.parts[1]
        folder_slug = rel.parts[2]

        try:
            content = index_md.read_text(encoding="utf-8")
        except Exception as e:
            records.append({
                "index_path": str(index_md),
                "folder_slug": folder_slug,
                "error": str(e),
                "classification": NEEDS_REVIEW,
            })
            continue

        fm = _parse_frontmatter(content)
        title = fm.get("title", "")
        date = fm.get("date", "")
        draft = fm.get("draft", False)
        grade = fm.get("grade", "")
        provenance = fm.get("provenance") or {}
        auto_updatable = provenance.get("auto_updatable", True)
        content_origin = provenance.get("content_origin", "skill-generated")

        classification = classify_folder_slug_quality(
            folder_slug=folder_slug,
            title=title,
            family=family,
            platform=platform,
            auto_updatable=auto_updatable,
            content_origin=content_origin,
        )

        # Count locale siblings
        folder = index_md.parent
        locale_count = _count_locale_files(folder)

        # Propose repair if MIGRATION_READY
        repair_candidate = None
        repair_blocked_reason = None
        if classification == MIGRATION_READY:
            repair_candidate = propose_folder_slug_repair(
                old_slug=folder_slug,
                title=title,
                family=family,
                platform=platform,
            )
            # Validate the repair
            violations = validate_folder_slug(repair_candidate, title, family, platform)
            if violations:
                repair_blocked_reason = "; ".join(violations)
                repair_candidate = None

        elif classification in {BLOCKED_BY_GOVERNANCE}:
            repair_blocked_reason = "auto_updatable=false or manual-remediation origin"
        elif classification in {NEEDS_REVIEW, BAD_NO_PLATFORM}:
            repair_blocked_reason = f"classification={classification} — human review required"

        inferred_url = build_blog_url_from_index_path(index_md)

        source_file_value = f"blog.aspose.org/{family}/{platform}/{folder_slug}/index.md"
        locale_files_with_ref = _count_source_file_refs(folder, source_file_value)

        record = {
            "index_path": str(index_md.as_posix()),
            "folder_slug": folder_slug,
            "inferred_url": inferred_url,
            "title": title,
            "family": family,
            "platform": platform,
            "date": str(date) if date else "",
            "draft": draft,
            "grade": grade,
            "auto_updatable": auto_updatable,
            "content_origin": content_origin,
            "classification": classification,
            "repair_candidate": repair_candidate,
            "repair_blocked_reason": repair_blocked_reason,
            "locale_file_count": locale_count,
            "source_file_refs_to_update": [str(f.as_posix()) for f in locale_files_with_ref],
        }
        records.append(record)
    return records


def build_repair_candidates(records: list[dict], blog_root: Path) -> list[dict]:
    """Build repair candidates list from MIGRATION_READY records with a valid repair_candidate."""
    candidates = []
    for rec in records:
        if rec.get("classification") != MIGRATION_READY:
            continue
        if not rec.get("repair_candidate"):
            continue

        family = rec["family"]
        platform = rec["platform"]
        old_slug = rec["folder_slug"]
        new_slug = rec["repair_candidate"]

        old_path = f"content/blog.aspose.org/{family}/{platform}/{old_slug}"
        new_path = f"content/blog.aspose.org/{family}/{platform}/{new_slug}"

        # Locale files
        folder = blog_root / family / platform / old_slug
        locale_files = [str(f.as_posix()) for f in sorted(folder.glob("index.*.md")) if _is_locale_file(f)]

        # source_file updates
        old_sf = f"blog.aspose.org/{family}/{platform}/{old_slug}/index.md"
        new_sf = f"blog.aspose.org/{family}/{platform}/{new_slug}/index.md"
        source_file_updates = []
        for lf in locale_files:
            source_file_updates.append({
                "file": lf,
                "old_value": old_sf,
                "new_value": new_sf,
            })

        candidates.append({
            "old_folder_slug": old_slug,
            "new_folder_slug": new_slug,
            "old_path": old_path,
            "new_path": new_path,
            "title": rec["title"],
            "family": family,
            "platform": platform,
            "grade": rec["grade"],
            "auto_updatable": rec["auto_updatable"],
            "locale_files": locale_files,
            "source_file_updates": source_file_updates,
            "inbound_link_updates": [],  # populated by migration tool if needed
        })
    return candidates


def build_markdown_report(records: list[dict], candidates: list[dict]) -> str:
    """Build a human-readable Markdown inventory report."""
    counts: dict[str, int] = {}
    for r in records:
        c = r.get("classification", "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1

    lines = [
        "# Blog Folder Slug Inventory",
        "",
        f"Total posts scanned: **{len(records)}**",
        "",
        "## Summary",
        "",
        "| Classification | Count |",
        "|----------------|-------|",
    ]
    for cls in [OK, WEAK, BAD_GENERIC, BAD_FALLBACK, BAD_NO_PLATFORM, BAD_TOO_SHORT,
                MIGRATION_READY, NEEDS_REVIEW, BLOCKED_BY_GOVERNANCE]:
        if cls in counts:
            lines.append(f"| {cls} | {counts[cls]} |")

    lines += [
        "",
        "## Migration-Ready Repair Candidates",
        "",
    ]
    if candidates:
        lines += [
            "| Old Slug | New Slug | Family/Platform | Title |",
            "|----------|----------|----------------|-------|",
        ]
        for c in candidates:
            lines.append(
                f"| `{c['old_folder_slug']}` | `{c['new_folder_slug']}` "
                f"| {c['family']}/{c['platform']} | {c['title']} |"
            )
    else:
        lines.append("_No migration-ready candidates._")

    lines += [
        "",
        "## All Posts",
        "",
        "| Folder Slug | Family/Platform | Classification | Title |",
        "|------------|----------------|----------------|-------|",
    ]
    for r in records:
        lines.append(
            f"| `{r['folder_slug']}` | {r.get('family','')}/{r.get('platform','')} "
            f"| {r.get('classification','?')} | {r.get('title','')[:60]} |"
        )

    lines.append("")

    # Intentionally unchanged WEAK and NEEDS_REVIEW
    unchanged = [r for r in records if r.get("classification") in {WEAK, NEEDS_REVIEW, BAD_NO_PLATFORM}]
    if unchanged:
        lines += [
            "## Intentionally Unchanged Slugs (WEAK / NEEDS_REVIEW / BAD_NO_PLATFORM)",
            "",
            "These slugs are imperfect but were NOT renamed in this sprint.",
            "They require human review before any rename can proceed.",
            "",
            "| Folder Slug | Classification | Reason |",
            "|------------|----------------|--------|",
        ]
        for r in unchanged:
            reason = r.get("repair_blocked_reason") or "Protected — see sprint scope"
            lines.append(
                f"| `{r['folder_slug']}` | {r['classification']} | {reason} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan blog.aspose.org for bad folder slugs"
    )
    parser.add_argument("--root", default="content/blog.aspose.org",
                        help="Path to blog.aspose.org content root")
    parser.add_argument("--out", default="reports/blog-slugs",
                        help="Output directory for reports")
    args = parser.parse_args()

    blog_root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()

    if not blog_root.is_dir():
        print(f"ERROR: blog root not found: {blog_root}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {blog_root} ...", file=sys.stderr)
    records = scan_posts(blog_root)
    print(f"  Found {len(records)} English posts", file=sys.stderr)

    candidates = build_repair_candidates(records, blog_root)
    print(f"  Migration-ready candidates: {len(candidates)}", file=sys.stderr)

    # Write JSON inventory
    inv_json = out_dir / "blog-folder-slug-inventory.json"
    inv_json.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    print(f"  Written: {inv_json}", file=sys.stderr)

    # Write Markdown inventory
    inv_md = out_dir / "blog-folder-slug-inventory.md"
    inv_md.write_text(build_markdown_report(records, candidates), encoding="utf-8")
    print(f"  Written: {inv_md}", file=sys.stderr)

    # Write repair candidates
    cand_json = out_dir / "blog-folder-slug-repair-candidates.json"
    cand_json.write_text(json.dumps(candidates, indent=2, default=str), encoding="utf-8")
    print(f"  Written: {cand_json}", file=sys.stderr)

    # Summary to stdout
    counts: dict[str, int] = {}
    for r in records:
        c = r.get("classification", "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1

    print(f"\nInventory summary ({len(records)} posts):")
    for cls, n in sorted(counts.items()):
        print(f"  {cls}: {n}")
    print(f"\nMigration-ready: {len(candidates)}")
    if candidates:
        for c in candidates:
            print(f"  {c['old_folder_slug']} -> {c['new_folder_slug']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
