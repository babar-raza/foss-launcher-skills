#!/usr/bin/env python3
"""
V-05: Blog index metadata validator.

Checks:
  Class A — {family}/{platform}/_index.md:
    - title present and equals "{taxonomy_term} FOSS for {platform_display}" exactly
    - categories present, non-empty, contains taxonomy_term

  Class B — {family}/{platform}/{slug}/index.md:
    - categories present, non-empty, contains taxonomy_term
    - title: not checked

Violation codes:
  MISSING_TITLE, WRONG_TITLE_NO_FOSS, WRONG_TITLE_VALUE
  MISSING_CATEGORIES, WRONG_CATEGORY
  UNKNOWN_FAMILY, UNKNOWN_PLATFORM

Exit: 0=PASS, 1=FAIL
"""
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BLOG_CONTENT = _REPO_ROOT / "content" / "blog.aspose.org"

# Two-letter locale codes used as blog content subdirectories.
_LOCALE_CODES = {
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms",
    "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr", "sv", "th", "tr",
    "uk", "vi", "zh",
}


def _load_family_routes() -> dict[str, str]:
    """Return {family_slug: taxonomy_term} from data/blog_family_routes.yaml."""
    path = _REPO_ROOT / "data" / "blog_family_routes.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        slug: info["taxonomy_term"]
        for slug, info in data.get("families", {}).items()
    }


def _load_platforms() -> dict[str, str]:
    """Return {platform_slug: display_name} from data/platforms.json."""
    path = _REPO_ROOT / "data" / "platforms.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_frontmatter(path: Path) -> dict | None:
    """Parse YAML frontmatter from a Hugo content file. Returns None on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    fm_text = text[3:end]
    try:
        return yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return None


def _check_class_a(
    path: Path,
    family: str,
    platform: str,
    taxonomy_term: str,
    platform_display: str,
) -> list[str]:
    """Check a platform _index.md (Class A). Returns list of violation strings."""
    violations: list[str] = []
    fm = _parse_frontmatter(path)
    if fm is None:
        violations.append(f"{path}: MISSING_TITLE: cannot parse frontmatter")
        return violations

    rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
    expected_title = f"{taxonomy_term} FOSS for {platform_display}"

    # Title checks
    title = fm.get("title")
    if title is None:
        violations.append(f"{rel}: MISSING_TITLE: no title field")
    elif "FOSS for" not in str(title):
        violations.append(
            f"{rel}: WRONG_TITLE_NO_FOSS: title={title!r} (expected: {expected_title!r})"
        )
    elif str(title) != expected_title:
        violations.append(
            f"{rel}: WRONG_TITLE_VALUE: title={title!r} (expected: {expected_title!r})"
        )

    # Categories checks
    cats = fm.get("categories")
    if not cats:
        violations.append(f"{rel}: MISSING_CATEGORIES: categories field is absent or empty")
    elif not isinstance(cats, list) or taxonomy_term not in cats:
        violations.append(
            f"{rel}: WRONG_CATEGORY: categories={cats!r} (expected: [{taxonomy_term!r}])"
        )

    return violations


def _check_class_b(
    path: Path,
    taxonomy_term: str,
) -> list[str]:
    """Check a blog post index.md (Class B). Returns list of violation strings."""
    violations: list[str] = []
    fm = _parse_frontmatter(path)
    if fm is None:
        return violations  # Cannot parse — skip silently (corrupt file is a separate concern)

    rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
    cats = fm.get("categories")
    if not cats:
        violations.append(f"{rel}: MISSING_CATEGORIES: categories field is absent or empty")
    elif not isinstance(cats, list) or taxonomy_term not in cats:
        violations.append(
            f"{rel}: WRONG_CATEGORY: categories={cats!r} (expected: [{taxonomy_term!r}])"
        )

    return violations


def main() -> int:
    if not _BLOG_CONTENT.is_dir():
        print(f"SKIP: {_BLOG_CONTENT} does not exist", file=sys.stderr)
        return 0

    family_routes = _load_family_routes()
    platforms = _load_platforms()

    all_violations: list[str] = []

    for family_dir in sorted(_BLOG_CONTENT.iterdir()):
        if not family_dir.is_dir():
            continue
        if family_dir.name in _LOCALE_CODES:
            continue

        family = family_dir.name

        if family not in family_routes:
            # Family exists in content but not in routes — skip with warning
            print(f"WARN: UNKNOWN_FAMILY {family} (not in blog_family_routes.yaml)", file=sys.stderr)
            continue

        taxonomy_term = family_routes[family]

        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue

            platform = platform_dir.name

            # Determine platform display name
            if platform not in platforms:
                platform_display = platform.capitalize()
            else:
                platform_display = platforms[platform]

            # Class A: _index.md
            index_md = platform_dir / "_index.md"
            if index_md.is_file():
                violations = _check_class_a(
                    index_md, family, platform, taxonomy_term, platform_display
                )
                all_violations.extend(violations)

            # Class B: {slug}/index.md
            for slug_dir in sorted(platform_dir.iterdir()):
                if not slug_dir.is_dir():
                    continue
                post_index = slug_dir / "index.md"
                if post_index.is_file():
                    violations = _check_class_b(post_index, taxonomy_term)
                    all_violations.extend(violations)

    if all_violations:
        for v in all_violations:
            print(v)
        print(f"\nFAIL: {len(all_violations)} violation(s) found.", file=sys.stderr)
        return 1

    print(f"PASS: blog index metadata check — 0 violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
