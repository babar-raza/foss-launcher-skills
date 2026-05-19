#!/usr/bin/env python3
"""
Blog family route coverage check.

Verifies every blog content family directory has a matching entry in
data/blog_family_routes.yaml.  Catches the /font/-class bug where a
family is launched but the routes YAML is not updated, causing the
section template to render an empty corporate page.

Exit code: 0 if all content families are covered, 1 if any are missing.
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed — run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BLOG_CONTENT = _REPO_ROOT / "content" / "blog.aspose.org"
_ROUTES_YAML = _REPO_ROOT / "data" / "blog_family_routes.yaml"

# Two-letter locale codes used as blog content subdirectories.
# These are NOT family directories and must be excluded.
_LOCALE_CODES = {
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms",
    "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr", "sv", "th", "tr",
    "uk", "vi", "zh",
}


def main() -> int:
    if not _BLOG_CONTENT.is_dir():
        print(f"SKIP: {_BLOG_CONTENT} does not exist", file=sys.stderr)
        return 0

    if not _ROUTES_YAML.is_file():
        print(f"FAIL: {_ROUTES_YAML} not found", file=sys.stderr)
        return 1

    with open(_ROUTES_YAML) as f:
        data = yaml.safe_load(f)

    registered = set(data.get("families", {}).keys())

    # Find family directories: subdirs of blog content root that are not
    # locale codes and contain at least one .md file (directly or nested).
    content_families: set[str] = set()
    for child in sorted(_BLOG_CONTENT.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name in _LOCALE_CODES:
            continue
        if any(child.rglob("*.md")):
            content_families.add(name)

    missing = content_families - registered
    if missing:
        print(f"FAIL: {len(missing)} blog content family dir(s) missing from {_ROUTES_YAML.name}:")
        for m in sorted(missing):
            print(f"  {m}/  (has content but no entry in blog_family_routes.yaml)")
        print(f"\nFix: add entries for {sorted(missing)} to data/blog_family_routes.yaml")
        return 1

    extra = registered - content_families
    if extra:
        print(f"INFO: {len(extra)} pre-registered families with no blog content yet: {sorted(extra)}")

    print(f"PASS: all {len(content_families)} blog content families covered ({len(registered)} registered total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
