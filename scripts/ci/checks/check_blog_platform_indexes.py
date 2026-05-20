#!/usr/bin/env python3
"""
Blog platform _index.md existence check.

Verifies every blog platform sub-directory that contains blog posts also
has an _index.md branch bundle.  Without _index.md, Hugo does not generate
section index pages for nested sub-sections (depth >= 2), causing 404s on
routes like /words/python/ or /cells/java/.

Exit code: 0 if all platform dirs have _index.md, 1 if any are missing.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BLOG_CONTENT = _REPO_ROOT / "content" / "blog.aspose.org"

# Two-letter locale codes used as blog content subdirectories.
_LOCALE_CODES = {
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms",
    "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr", "sv", "th", "tr",
    "uk", "vi", "zh",
}


def _has_blog_posts(platform_dir: Path) -> bool:
    """Return True if platform_dir contains at least one blog post.

    Blog posts are slug/index.md directories (Hugo leaf bundles) nested
    directly under the platform directory.
    """
    for child in platform_dir.iterdir():
        if child.is_dir() and (child / "index.md").is_file():
            return True
    return False


def main() -> int:
    if not _BLOG_CONTENT.is_dir():
        print(f"SKIP: {_BLOG_CONTENT} does not exist", file=sys.stderr)
        return 0

    missing: list[str] = []

    for family_dir in sorted(_BLOG_CONTENT.iterdir()):
        if not family_dir.is_dir():
            continue
        if family_dir.name in _LOCALE_CODES:
            continue

        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if not _has_blog_posts(platform_dir):
                continue
            if not (platform_dir / "_index.md").is_file():
                rel = platform_dir.relative_to(_REPO_ROOT)
                missing.append(str(rel).replace("\\", "/"))

    if missing:
        print(f"FAIL: {len(missing)} blog platform dir(s) missing _index.md:")
        for m in sorted(missing):
            print(f"  {m}/_index.md")
        print(
            "\nWithout _index.md, Hugo does not generate section index pages"
            " for nested sub-sections (depth >= 2), causing 404s."
        )
        print("Fix: add a minimal _index.md with title frontmatter to each directory.")
        return 1

    # Count how many platform dirs were checked
    checked = 0
    for family_dir in _BLOG_CONTENT.iterdir():
        if not family_dir.is_dir() or family_dir.name in _LOCALE_CODES:
            continue
        for platform_dir in family_dir.iterdir():
            if platform_dir.is_dir() and _has_blog_posts(platform_dir):
                checked += 1

    print(f"PASS: all {checked} blog platform sub-directories have _index.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
