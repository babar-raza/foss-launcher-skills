#!/usr/bin/env python3
"""
fix_blog_index_metadata.py — Repair blog FOSS title and categories metadata.

CLI:
  python fix_blog_index_metadata.py [--dry-run | --apply]

Default: --dry-run (print proposed changes, write nothing)
--apply: write changes to disk

Class A ({family}/{platform}/_index.md):
  - Sets title = "{taxonomy_term} FOSS for {platform_display}"
  - Sets categories = [taxonomy_term]

Class B ({family}/{platform}/{slug}/index.md):
  - Sets categories = [taxonomy_term]
  - Title is NOT changed

Data sources (read-only):
  data/blog_family_routes.yaml  -> taxonomy_term per family
  data/platforms.json           -> platform display name per slug

Exit: 0 always (errors per-file reported but do not halt)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BLOG_CONTENT = _REPO_ROOT / "content" / "blog.aspose.org"

_LOCALE_CODES = {
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms",
    "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr", "sv", "th", "tr",
    "uk", "vi", "zh",
}


def _load_family_routes() -> dict[str, str]:
    path = _REPO_ROOT / "data" / "blog_family_routes.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        slug: info["taxonomy_term"]
        for slug, info in data.get("families", {}).items()
    }


def _load_platforms() -> dict[str, str]:
    path = _REPO_ROOT / "data" / "platforms.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split file text into (frontmatter_text, body). Returns None if no frontmatter."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    fm = text[3:end]
    body = text[end + 3:]
    return fm, body


def _rewrite_file(path: Path, new_fm_dict: dict, original_fm_text: str, body: str) -> str:
    """Serialize updated frontmatter dict back, preserving field order."""
    new_fm = yaml.dump(
        new_fm_dict,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{new_fm}---{body}"


def _fix_class_a(
    path: Path,
    taxonomy_term: str,
    platform_display: str,
    dry_run: bool,
) -> str:
    """Fix a platform _index.md. Returns "SKIP", "FIXED", or "ERROR: <msg>"."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return f"ERROR: {e}"

    split = _split_frontmatter(text)
    if split is None:
        return "ERROR: no YAML frontmatter"

    fm_text, body = split
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        return f"ERROR: YAML parse error: {e}"

    expected_title = f"{taxonomy_term} FOSS for {platform_display}"
    expected_cats = [taxonomy_term]

    current_title = fm.get("title")
    current_cats = fm.get("categories")

    already_correct = (
        current_title == expected_title
        and isinstance(current_cats, list)
        and current_cats == expected_cats
    )
    if already_correct:
        return "SKIP"

    fm["title"] = expected_title
    fm["categories"] = expected_cats

    if not dry_run:
        new_text = _rewrite_file(path, fm, fm_text, body)
        path.write_text(new_text, encoding="utf-8")

    return "FIXED"


def _fix_class_b(
    path: Path,
    taxonomy_term: str,
    dry_run: bool,
) -> str:
    """Fix a blog post index.md. Returns "SKIP", "FIXED", or "ERROR: <msg>"."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return f"ERROR: {e}"

    split = _split_frontmatter(text)
    if split is None:
        return "ERROR: no YAML frontmatter"

    fm_text, body = split
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        return f"ERROR: YAML parse error: {e}"

    expected_cats = [taxonomy_term]
    current_cats = fm.get("categories")

    if isinstance(current_cats, list) and current_cats == expected_cats:
        return "SKIP"

    fm["categories"] = expected_cats

    if not dry_run:
        new_text = _rewrite_file(path, fm, fm_text, body)
        path.write_text(new_text, encoding="utf-8")

    return "FIXED"


def main(dry_run: bool = True) -> int:
    family_routes = _load_family_routes()
    platforms = _load_platforms()

    index_fixed = 0
    index_skipped = 0
    posts_fixed = 0
    posts_skipped = 0
    errors = 0

    mode_label = "DRY-RUN" if dry_run else "APPLY"

    for family_dir in sorted(_BLOG_CONTENT.iterdir()):
        if not family_dir.is_dir():
            continue
        if family_dir.name in _LOCALE_CODES:
            continue

        family = family_dir.name
        if family not in family_routes:
            continue

        taxonomy_term = family_routes[family]

        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue

            platform = platform_dir.name
            platform_display = platforms.get(platform, platform.capitalize())

            # Class A: _index.md
            index_md = platform_dir / "_index.md"
            if index_md.is_file():
                result = _fix_class_a(index_md, taxonomy_term, platform_display, dry_run)
                rel = str(index_md.relative_to(_REPO_ROOT)).replace("\\", "/")
                if result == "FIXED":
                    print(f"{mode_label} FIXED(A) {rel}: title->'{taxonomy_term} FOSS for {platform_display}', categories->['{taxonomy_term}']")
                    index_fixed += 1
                elif result == "SKIP":
                    index_skipped += 1
                else:
                    print(f"{mode_label} {result} {rel}", file=sys.stderr)
                    errors += 1

            # Class B: {slug}/index.md
            for slug_dir in sorted(platform_dir.iterdir()):
                if not slug_dir.is_dir():
                    continue
                post_index = slug_dir / "index.md"
                if not post_index.is_file():
                    continue
                result = _fix_class_b(post_index, taxonomy_term, dry_run)
                rel = str(post_index.relative_to(_REPO_ROOT)).replace("\\", "/")
                if result == "FIXED":
                    print(f"{mode_label} FIXED(B) {rel}: categories->['{taxonomy_term}']")
                    posts_fixed += 1
                elif result == "SKIP":
                    posts_skipped += 1
                else:
                    print(f"{mode_label} {result} {rel}", file=sys.stderr)
                    errors += 1

    print(
        f"\nSummary ({mode_label}): "
        f"{index_fixed} _index.md fixed, {posts_fixed} posts fixed, "
        f"{index_skipped} _index.md skipped, {posts_skipped} posts skipped, "
        f"{errors} error(s)."
    )
    if dry_run:
        print("(dry-run: no files written)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair blog FOSS title and categories metadata.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Print proposed changes without writing (default)")
    group.add_argument("--apply", action="store_true", default=False,
                       help="Apply changes to disk")
    args = parser.parse_args()
    dry_run = not args.apply
    sys.exit(main(dry_run=dry_run))
