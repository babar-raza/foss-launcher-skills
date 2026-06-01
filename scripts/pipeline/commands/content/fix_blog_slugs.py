#!/usr/bin/env python3
"""fix_blog_slugs.py — Apply SEO-optimized slug renames to blog posts.

Renames blog post directories to AI-generated or manually specified slugs,
adds Hugo aliases for URL stability, and sets explicit canonical URLs.

Usage:
    # Dry-run: show what would change (no LLM, uses deterministic proposals)
    python scripts/pipeline/commands/content/fix_blog_slugs.py --dry-run

    # Dry-run with AI proposals:
    python scripts/pipeline/commands/content/fix_blog_slugs.py --dry-run --ai

    # Apply worst 5 slugs:
    python scripts/pipeline/commands/content/fix_blog_slugs.py --apply --ai --top 5

    # Apply specific family/platform:
    python scripts/pipeline/commands/content/fix_blog_slugs.py --apply --ai --family cells --platform python

    # Override a specific slug:
    python scripts/pipeline/commands/content/fix_blog_slugs.py --apply --override cells/python/introducing-cells-foss-python=python-excel-xlsx-library
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

import yaml  # noqa: E402
from lib.blog_slug_policy import generate_seo_slug, validate_seo_slug  # noqa: E402
from commands.diagnostics.audit_blog_slugs import (  # noqa: E402
    BlogPost,
    classify_seo_pattern,
    scan_blog_posts,
    _SEO_SEVERITY,
)

# ---------------------------------------------------------------------------
# Frontmatter manipulation
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)


def _update_frontmatter(
    text: str,
    old_slug: str,
    new_slug: str,
    family: str,
    platform: str,
) -> str:
    """Update frontmatter with aliases and url for a slug rename.

    Adds:
      aliases: [/{family}/{platform}/{old_slug}/]
      url: /{family}/{platform}/{new_slug}/
    """
    m = _FM_RE.match(text)
    if not m:
        raise ValueError("No frontmatter block found")

    fm_text = m.group(2)
    fm = yaml.safe_load(fm_text) or {}

    # Set aliases (preserve existing, append old path)
    old_path = f"/{family}/{platform}/{old_slug}/"
    existing_aliases = fm.get("aliases", []) or []
    if isinstance(existing_aliases, str):
        existing_aliases = [existing_aliases]
    if old_path not in existing_aliases:
        existing_aliases.append(old_path)
    fm["aliases"] = existing_aliases

    # Set canonical url
    fm["url"] = f"/{family}/{platform}/{new_slug}/"

    # Re-serialize frontmatter preserving key order as much as possible
    # We'll insert the new keys into the raw YAML text to minimize diff
    new_lines = []
    seen_aliases = False
    seen_url = False
    skip_alias_items = False

    for line in fm_text.split("\n"):
        key_match = re.match(r"^([a-z_]+)\s*:", line)
        if key_match:
            skip_alias_items = False
            key = key_match.group(1)
            if key == "aliases":
                seen_aliases = True
                skip_alias_items = True
                # Replace with new aliases
                if len(existing_aliases) == 1:
                    new_lines.append(f"aliases: [{existing_aliases[0]}]")
                else:
                    new_lines.append("aliases:")
                    for alias in existing_aliases:
                        new_lines.append(f"  - {alias}")
                continue
            if key == "url":
                seen_url = True
                new_lines.append(f"url: /{family}/{platform}/{new_slug}/")
                continue
        elif skip_alias_items and re.match(r"^(\s*- )", line):
            # Skip old alias list continuation items
            continue
        else:
            skip_alias_items = False
        new_lines.append(line)

    # Append missing keys before closing ---
    if not seen_aliases:
        if len(existing_aliases) == 1:
            new_lines.append(f"aliases: [{existing_aliases[0]}]")
        else:
            new_lines.append("aliases:")
            for alias in existing_aliases:
                new_lines.append(f"  - {alias}")
    if not seen_url:
        new_lines.append(f"url: /{family}/{platform}/{new_slug}/")

    new_fm = "\n".join(new_lines)
    return f"{m.group(1)}{new_fm}{m.group(3)}{text[m.end():]}"


# ---------------------------------------------------------------------------
# Slug application
# ---------------------------------------------------------------------------

def apply_slug_rename(
    content_root: Path,
    post: BlogPost,
    new_slug: str,
    *,
    dry_run: bool = True,
) -> dict:
    """Rename a blog post directory and update frontmatter.

    Returns a dict describing the change made (or that would be made).
    """
    blog_root = content_root / "blog.aspose.org"
    old_dir = blog_root / post.family / post.platform / post.slug
    new_dir = blog_root / post.family / post.platform / new_slug

    result = {
        "family": post.family,
        "platform": post.platform,
        "old_slug": post.slug,
        "new_slug": new_slug,
        "old_path": str(old_dir),
        "new_path": str(new_dir),
        "applied": False,
        "error": None,
    }

    if not old_dir.is_dir():
        result["error"] = f"Source directory not found: {old_dir}"
        return result

    if new_dir.exists():
        result["error"] = f"Target directory already exists: {new_dir}"
        return result

    if dry_run:
        result["applied"] = False
        return result

    # Read and update all markdown files in the directory
    for md_file in old_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        try:
            updated = _update_frontmatter(
                text, post.slug, new_slug, post.family, post.platform
            )
            md_file.write_text(updated, encoding="utf-8")
        except ValueError as exc:
            result["error"] = f"Frontmatter update failed for {md_file.name}: {exc}"
            return result

    # Rename directory
    shutil.move(str(old_dir), str(new_dir))
    result["applied"] = True
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Apply SEO slug renames to blog posts")
    parser.add_argument("--root", default=str(_REPO_ROOT / "content"),
                        help="Content root directory")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would change")
    mode.add_argument("--apply", action="store_true", help="Execute changes")
    parser.add_argument("--ai", action="store_true",
                        help="Use LLM to generate replacement slugs")
    parser.add_argument("--severity", default=None,
                        help="Comma-separated: introducing,key-features,working-with,generic-topic")
    parser.add_argument("--family", default=None, help="Filter by family")
    parser.add_argument("--platform", default=None, help="Filter by platform")
    parser.add_argument("--top", type=int, default=None, help="Only process N worst slugs")
    parser.add_argument("--override", action="append", default=[],
                        help="Manual override: family/platform/old-slug=new-slug")
    args = parser.parse_args()

    content_root = Path(args.root)
    posts = scan_blog_posts(content_root)
    if not posts:
        print("No blog posts found.", file=sys.stderr)
        return 1

    # Parse manual overrides
    overrides: dict[str, str] = {}
    for ov in args.override:
        if "=" not in ov:
            print(f"ERROR: Invalid override format: {ov} (expected key=value)", file=sys.stderr)
            return 1
        key, val = ov.split("=", 1)
        overrides[key] = val

    # Filter to posts needing change
    candidates = [p for p in posts if p.seo_pattern != "good"]

    if args.severity:
        sev_set = set(args.severity.split(","))
        candidates = [p for p in candidates if p.seo_pattern in sev_set]
    if args.family:
        candidates = [p for p in candidates if p.family == args.family]
    if args.platform:
        candidates = [p for p in candidates if p.platform == args.platform]

    # Sort worst first
    candidates.sort(key=lambda p: (
        _SEO_SEVERITY.get(p.seo_pattern, 99), p.family, p.platform
    ))

    if args.top:
        candidates = candidates[:args.top]

    # Generate proposed slugs
    router = None
    if args.ai:
        try:
            from commands.ops.llm_router import LLMRouter
            router = LLMRouter()
        except Exception as exc:
            print(f"WARNING: LLM unavailable ({exc}), using deterministic fallback",
                  file=sys.stderr)

    results = []
    for i, p in enumerate(candidates, 1):
        key = f"{p.family}/{p.platform}/{p.slug}"

        # Check for manual override first
        if key in overrides:
            new_slug = overrides[key]
        else:
            print(f"  [{i}/{len(candidates)}] Generating slug for {key}...", file=sys.stderr)
            new_slug = generate_seo_slug(
                title=p.title,
                description=p.description,
                summary=p.summary,
                family=p.family,
                platform=p.platform,
                llm_router=router,
            )

        violations = validate_seo_slug(new_slug)
        if violations:
            print(f"  WARNING: Proposed slug '{new_slug}' has violations: {violations}",
                  file=sys.stderr)

        # Apply or dry-run
        r = apply_slug_rename(
            content_root, p, new_slug,
            dry_run=not args.apply,
        )
        results.append(r)

        status = "APPLIED" if r["applied"] else "DRY-RUN" if not r["error"] else "ERROR"
        print(f"  {status}: {r['old_slug']} ->{r['new_slug']}"
              + (f" ({r['error']})" if r["error"] else ""))

    # Summary
    applied = sum(1 for r in results if r["applied"])
    errors = sum(1 for r in results if r["error"])
    dry_runs = sum(1 for r in results if not r["applied"] and not r["error"])

    print(f"\n{'='*40}")
    print(f"Total: {len(results)} | Applied: {applied} | Dry-run: {dry_runs} | Errors: {errors}")

    if dry_runs > 0 and not args.apply:
        print("\nRe-run with --apply to execute these changes.")

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
