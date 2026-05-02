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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
_FM_SPLIT_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)

# Depth: content/blog.aspose.org/{family}/{platform}/{slug}/index.md → 4 parts relative
_MIN_DEPTH = 4


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

@dataclass
class FrontmatterParseResult:
    """Result of parsing YAML frontmatter from a markdown file.

    Distinguishes four cases:
    - No FM block present:              has_frontmatter=False, valid=False
    - FM block present, YAML error:     has_frontmatter=True,  valid=False, error=<message>
    - FM block present, non-dict YAML:  has_frontmatter=True,  valid=False, error='not a mapping'
    - FM block present, valid dict:     has_frontmatter=True,  valid=True,  data=<dict>
    """
    has_frontmatter: bool
    valid: bool
    data: dict[str, Any]
    error: str | None
    raw: str  # raw text between --- delimiters


def parse_frontmatter(text: str) -> FrontmatterParseResult:
    """Parse YAML frontmatter. Never raises."""
    m = _FM_RE.match(text)
    if not m:
        return FrontmatterParseResult(
            has_frontmatter=False, valid=False, data={}, error=None, raw=""
        )
    raw = m.group(1)
    try:
        result = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return FrontmatterParseResult(
            has_frontmatter=True, valid=False, data={}, error=str(e), raw=raw
        )
    if not isinstance(result, dict):
        return FrontmatterParseResult(
            has_frontmatter=True, valid=False, data={},
            error=f"not a mapping (got {type(result).__name__})", raw=raw
        )
    return FrontmatterParseResult(
        has_frontmatter=True, valid=True, data=result, error=None, raw=raw
    )


# ---------------------------------------------------------------------------
# Frontmatter / body split
# ---------------------------------------------------------------------------

def _split_frontmatter_and_body(text: str) -> tuple[str, str]:
    """Split markdown text into (frontmatter_block, body).

    frontmatter_block includes --- delimiters.
    Contract: frontmatter_block + body == text always (lossless).
    """
    m = _FM_SPLIT_RE.match(text)
    if not m:
        return "", text
    fm_block = m.group(1) + m.group(2) + m.group(3)
    body = text[m.end():]
    return fm_block, body


# ---------------------------------------------------------------------------
# Inbound link detection (body text only)
# ---------------------------------------------------------------------------

def _find_slug_in_body(body: str, family: str, platform: str, slug: str) -> bool:
    """Return True if body contains a URL reference to /{family}/{platform}/{slug}.

    Operates on body text only (frontmatter already stripped).
    Prevents partial slug matches: slug must be followed by /, ?, #, ", ', ), whitespace, or EOL.
    Prevents path-prefix false positives: /blog/3d/java/slug must NOT match family=3d.
    The root-relative form requires a negative lookbehind — /{family} must not be preceded
    by a path-segment character (letter, digit, dot, underscore, hyphen, or slash).
    """
    esc_family = re.escape(family)
    esc_platform = re.escape(platform)
    esc_slug = re.escape(slug)
    tail = r"(?=[/?#\"'\)\s]|$)"

    # Absolute forms: domain must be matched exactly (not a substring)
    abs_form = (
        r"(?:https?://blog\.aspose\.org|//blog\.aspose\.org)"
        r"/" + esc_family + r"/" + esc_platform + r"/" + esc_slug + tail
    )
    # Root-relative form: /{family}/{platform}/{slug}
    # Negative lookbehind ensures we are NOT inside /blog/3d/... or any other prefix path
    root_form = (
        r"(?<![a-zA-Z0-9_./-])"
        r"/" + esc_family + r"/" + esc_platform + r"/" + esc_slug + tail
    )
    pattern = re.compile(r"(?:" + abs_form + r"|" + root_form + r")", re.IGNORECASE)
    return bool(pattern.search(body))


def _find_inbound_links(
    blog_root: Path,
    family: str,
    platform: str,
    folder_slug: str,
    own_folder: Path,
) -> list[str]:
    """Return sorted list of .md files (outside own_folder) whose body contains
    a URL reference to /{family}/{platform}/{folder_slug}/."""
    hits = []
    for md_file in sorted(blog_root.rglob("*.md")):
        # Skip files in the post's own folder
        try:
            md_file.relative_to(own_folder)
            continue  # inside own_folder — skip
        except ValueError:
            pass
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        _, body = _split_frontmatter_and_body(text)
        if _find_slug_in_body(body, family, platform, folder_slug):
            hits.append(str(md_file.as_posix()))
    return hits


# ---------------------------------------------------------------------------
# Locale file helpers
# ---------------------------------------------------------------------------

def _is_locale_file(path: Path) -> bool:
    """Return True if the file is a locale translation (e.g. index.ar.md)."""
    stem = path.stem
    if stem == "index":
        return False
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


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_posts(blog_root: Path) -> list[dict]:
    """Scan all English index.md posts under blog_root. Return list of post records.

    Each record includes:
    - Slug quality classification
    - Frontmatter parse diagnostics (has_frontmatter, frontmatter_valid, frontmatter_error)
    - Path shape validity
    - Inbound link count and file list (body links only — frontmatter excluded)
    - Candidate eligibility status and blockers
    - Existing aliases from frontmatter
    """
    records = []
    for index_md in sorted(blog_root.rglob("index.md")):
        rel = index_md.relative_to(blog_root)
        path_shape_valid = len(rel.parts) == _MIN_DEPTH

        # Record depth-invalid posts with diagnostics but do not process further
        if not path_shape_valid:
            family = rel.parts[0] if len(rel.parts) >= 1 else ""
            platform = rel.parts[1] if len(rel.parts) >= 2 else ""
            folder_slug = rel.parts[-2] if len(rel.parts) >= 2 else ""
            records.append({
                "index_path": str(index_md.as_posix()),
                "folder_slug": folder_slug,
                "family": family,
                "platform": platform,
                "path_shape_valid": False,
                "has_frontmatter": False,
                "frontmatter_valid": False,
                "frontmatter_error": None,
                "classification": NEEDS_REVIEW,
                "candidate_status": "EXCLUDED",
                "candidate_blockers": ["invalid-path-shape"],
                "candidate_warnings": [],
                "candidate_exclusion_reason": f"path depth {len(rel.parts)} != {_MIN_DEPTH}",
                "inbound_link_count": 0,
                "inbound_link_files": [],
                "aliases": [],
                "aliases_valid": True,
                "alias_notes": [],
                "title": "",
                "draft": False,
                "grade": "",
                "auto_updatable": False,
                "content_origin": "",
                "inferred_url": "",
                "repair_candidate": None,
                "repair_blocked_reason": f"path depth {len(rel.parts)} != {_MIN_DEPTH}",
                "locale_file_count": 0,
                "source_file_refs_to_update": [],
            })
            continue

        family = rel.parts[0]
        platform = rel.parts[1]
        folder_slug = rel.parts[2]
        folder = index_md.parent

        try:
            content = index_md.read_text(encoding="utf-8")
        except Exception as e:
            records.append({
                "index_path": str(index_md.as_posix()),
                "folder_slug": folder_slug,
                "family": family,
                "platform": platform,
                "path_shape_valid": True,
                "has_frontmatter": False,
                "frontmatter_valid": False,
                "frontmatter_error": str(e),
                "error": str(e),
                "classification": NEEDS_REVIEW,
                "candidate_status": "EXCLUDED",
                "candidate_blockers": ["read-error"],
                "candidate_warnings": [],
                "candidate_exclusion_reason": f"file read error: {e}",
                "inbound_link_count": 0,
                "inbound_link_files": [],
                "aliases": [],
                "aliases_valid": True,
                "alias_notes": [],
                "title": "",
                "draft": False,
                "grade": "",
                "auto_updatable": False,
                "content_origin": "",
                "inferred_url": "",
                "repair_candidate": None,
                "repair_blocked_reason": None,
                "locale_file_count": 0,
                "source_file_refs_to_update": [],
            })
            continue

        fm_result = parse_frontmatter(content)

        # Extract fields — only trust values from valid frontmatter
        if fm_result.valid:
            fm = fm_result.data
            title = fm.get("title", "")
            date = fm.get("date", "")
            draft = fm.get("draft", False)
            grade = fm.get("grade", "")
            provenance = fm.get("provenance") or {}
            auto_updatable = provenance.get("auto_updatable", True)
            content_origin = provenance.get("content_origin", "skill-generated")
            raw_aliases = fm.get("aliases", [])
            if isinstance(raw_aliases, list):
                aliases = [str(a) for a in raw_aliases]
                aliases_valid = True
            else:
                aliases = []
                aliases_valid = False
        else:
            # Invalid FM: use safe defaults but migration is blocked via candidate_blockers
            title = ""
            date = ""
            draft = False
            grade = ""
            auto_updatable = True  # unused — blocked via frontmatter_valid check
            content_origin = "skill-generated"
            aliases = []
            aliases_valid = True

        # Classify slug quality
        if fm_result.valid:
            classification = classify_folder_slug_quality(
                folder_slug=folder_slug,
                title=title,
                family=family,
                platform=platform,
                auto_updatable=auto_updatable,
                content_origin=content_origin,
            )
        else:
            classification = NEEDS_REVIEW

        # Build candidate blockers
        candidate_blockers: list[str] = []
        candidate_warnings: list[str] = []

        if not fm_result.has_frontmatter:
            candidate_blockers.append("no-frontmatter")
        elif not fm_result.valid:
            candidate_blockers.append("malformed-frontmatter")

        # draft check: treat True or "true" (string) as draft
        is_draft = (draft is True) or (isinstance(draft, str) and draft.lower() == "true")
        if is_draft:
            candidate_blockers.append("draft")

        if fm_result.valid and not auto_updatable:
            candidate_blockers.append("auto-updatable-false")

        if classification == BLOCKED_BY_GOVERNANCE and "auto-updatable-false" not in candidate_blockers:
            candidate_blockers.append("governance-block")

        # Determine candidate_status
        if candidate_blockers:
            candidate_status = "BLOCKED"
            candidate_exclusion_reason: str | None = "; ".join(candidate_blockers)
        elif classification == MIGRATION_READY:
            candidate_status = "ELIGIBLE"
            candidate_exclusion_reason = None
        elif classification == BLOCKED_BY_GOVERNANCE:
            candidate_status = "BLOCKED"
            candidate_exclusion_reason = "governance-block"
        else:
            candidate_status = "EXCLUDED"
            candidate_exclusion_reason = f"classification={classification}"

        # Propose repair (only for ELIGIBLE)
        repair_candidate: str | None = None
        repair_blocked_reason: str | None = None

        if candidate_status == "ELIGIBLE":
            repair_candidate = propose_folder_slug_repair(
                old_slug=folder_slug,
                title=title,
                family=family,
                platform=platform,
            )
            violations = validate_folder_slug(repair_candidate, title, family, platform)
            if violations:
                repair_blocked_reason = "; ".join(violations)
                repair_candidate = None
                candidate_status = "BLOCKED"
                candidate_blockers.append("repair-validation-failed")
                candidate_exclusion_reason = repair_blocked_reason
        elif classification in {BLOCKED_BY_GOVERNANCE}:
            repair_blocked_reason = "auto_updatable=false or manual-remediation origin"
        elif classification in {NEEDS_REVIEW, BAD_NO_PLATFORM}:
            repair_blocked_reason = f"classification={classification} — human review required"

        # Inbound link detection (body only)
        inbound_files = _find_inbound_links(blog_root, family, platform, folder_slug, folder)

        # Alias notes
        alias_notes: list[str] = []
        own_url = f"/{family}/{platform}/{folder_slug}/"
        if own_url in aliases:
            alias_notes.append(f"already has own-url alias: {own_url}")

        inferred_url = build_blog_url_from_index_path(index_md)

        source_file_value = f"blog.aspose.org/{family}/{platform}/{folder_slug}/index.md"
        locale_files_with_ref = _count_source_file_refs(folder, source_file_value)
        locale_count = _count_locale_files(folder)

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
            "path_shape_valid": path_shape_valid,
            "has_frontmatter": fm_result.has_frontmatter,
            "frontmatter_valid": fm_result.valid,
            "frontmatter_error": fm_result.error,
            "repair_candidate": repair_candidate,
            "repair_blocked_reason": repair_blocked_reason,
            "locale_file_count": locale_count,
            "source_file_refs_to_update": [str(f.as_posix()) for f in locale_files_with_ref],
            "inbound_link_count": len(inbound_files),
            "inbound_link_files": inbound_files,
            "candidate_status": candidate_status,
            "candidate_blockers": candidate_blockers,
            "candidate_warnings": candidate_warnings,
            "candidate_exclusion_reason": candidate_exclusion_reason,
            "aliases": aliases,
            "aliases_valid": aliases_valid,
            "alias_notes": alias_notes,
        }
        records.append(record)
    return records


def build_repair_candidates(records: list[dict], blog_root: Path) -> list[dict]:
    """Build repair candidates list from ELIGIBLE records.

    Policy:
    - Only posts with candidate_status == ELIGIBLE appear here.
    - ELIGIBLE requires: frontmatter_valid=True, path_shape_valid=True,
      draft=False/absent, auto_updatable=True, classification=MIGRATION_READY,
      and a valid repair_candidate slug.
    - Draft posts (draft: true or draft: "true") are excluded.
    - Malformed or missing frontmatter posts are excluded.
    - Each candidate has alias_required=True and required_alias=old_url.
    - inbound_link_updates is populated from the actual scan results.
    """
    candidates = []
    for rec in records:
        if rec.get("candidate_status") != "ELIGIBLE":
            continue
        if not rec.get("repair_candidate"):
            continue

        family = rec["family"]
        platform = rec["platform"]
        old_slug = rec["folder_slug"]
        new_slug = rec["repair_candidate"]

        old_path = f"content/blog.aspose.org/{family}/{platform}/{old_slug}"
        new_path = f"content/blog.aspose.org/{family}/{platform}/{new_slug}"

        old_url = f"/{family}/{platform}/{old_slug}/"
        new_url = f"/{family}/{platform}/{new_slug}/"

        # Locale files
        folder = blog_root / family / platform / old_slug
        locale_files = [
            str(f.as_posix())
            for f in sorted(folder.glob("index.*.md"))
            if _is_locale_file(f)
        ]

        # source_file updates
        old_sf = f"blog.aspose.org/{family}/{platform}/{old_slug}/index.md"
        new_sf = f"blog.aspose.org/{family}/{platform}/{new_slug}/index.md"
        source_file_updates = [
            {"file": lf, "old_value": old_sf, "new_value": new_sf}
            for lf in locale_files
        ]

        # Inbound link updates from actual scan
        inbound_link_updates = [
            {"file": f, "old_url": old_url, "new_url": new_url}
            for f in rec.get("inbound_link_files", [])
        ]

        candidates.append({
            "old_folder_slug": old_slug,
            "new_folder_slug": new_slug,
            "old_path": old_path,
            "new_path": new_path,
            "old_url": old_url,
            "new_url": new_url,
            "required_alias": old_url,
            "alias_required": True,
            "title": rec["title"],
            "family": family,
            "platform": platform,
            "grade": rec["grade"],
            "auto_updatable": rec["auto_updatable"],
            "candidate_status": "ELIGIBLE",
            "locale_files": locale_files,
            "source_file_updates": source_file_updates,
            "inbound_link_updates": inbound_link_updates,
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
            "| Old Slug | New Slug | Family/Platform | Title | Required Alias |",
            "|----------|----------|----------------|-------|----------------|",
        ]
        for c in candidates:
            lines.append(
                f"| `{c['old_folder_slug']}` | `{c['new_folder_slug']}` "
                f"| {c['family']}/{c['platform']} | {c['title']} "
                f"| `{c.get('required_alias', '')}` |"
            )
    else:
        lines.append("_No migration-ready candidates._")

    lines += [
        "",
        "## All Posts",
        "",
        "| Folder Slug | Family/Platform | Classification | Candidate Status | Title |",
        "|------------|----------------|----------------|-----------------|-------|",
    ]
    for r in records:
        lines.append(
            f"| `{r['folder_slug']}` | {r.get('family','')}/{r.get('platform','')} "
            f"| {r.get('classification','?')} | {r.get('candidate_status','?')} "
            f"| {r.get('title','')[:60]} |"
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
            print(f"  {c['old_folder_slug']} -> {c['new_folder_slug']}  (alias: {c['required_alias']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
