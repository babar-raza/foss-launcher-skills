#!/usr/bin/env python3
"""
Slug hygiene validator for blog.aspose.org.

Checks:
1. FAIL if any flat blog .md file's stem starts with 'test' (case-insensitive) —
   signals a slug derived from an internal test method name.
2. FAIL if any flat blog .md file exists that is not _index.md and not a translation —
   all leaf-level blog content must use the slug/index.md directory structure (P-05).
3. WARN if both a flat `{slug}.md` and a subdirectory `{slug}/index.md` exist at the
   same path — Hugo URL collision that produces unpredictable build output.
4. WARN if canonical: URL in frontmatter does not end with the file stem + '/'.
5. FAIL if any value in the `aliases:` frontmatter list contains a path segment whose
   final slug component starts with 'test' — signals test artifacts in aliases (P-06).

Exit code: 1 if any FAIL; 0 if only WARNs or clean.
"""

import re
import sys
from pathlib import Path

import yaml

BLOG_CONTENT_ROOT = Path(__file__).resolve().parents[3] / "content" / "blog.aspose.org"

# Frontmatter extraction
_FIRST_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)

# Language suffix — files like slug.de.md, slug.ar.md
RE_LANG_SUFFIX = re.compile(r"\.[a-z]{2}(-[a-zA-Z]{2,4})?$")


def is_translation(stem: str) -> bool:
    """Return True if the stem ends with a known language code suffix."""
    return bool(RE_LANG_SUFFIX.search(stem))


def extract_frontmatter(text: str) -> dict:
    """Return parsed frontmatter dict, or empty dict on failure."""
    m = _FIRST_FM_RE.match(text)
    if not m:
        return {}
    try:
        result = yaml.safe_load(m.group(1))
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        return {}


def collect_flat_english_files(root: Path) -> list[Path]:
    """Find all flat *.md files that are not _index.md and not translations.

    Only considers files at depth >= 3 inside root (i.e. inside {family}/{platform}/)
    to exclude root-level Hugo utility pages like archive.md and search.md.
    """
    results = []
    for md in root.rglob("*.md"):
        if md.name == "_index.md":
            continue
        stem = md.stem
        if is_translation(stem):
            continue
        # Directory-based pages are named index.md — those are compliant
        if md.name == "index.md":
            continue
        # Skip root-level utility pages (archive.md, search.md, etc.) —
        # these sit directly under blog.aspose.org/ and are intentionally flat.
        # Content posts live under {family}/{platform}/ (at least 2 levels deep).
        rel = md.relative_to(root)
        if len(rel.parts) < 3:
            continue
        results.append(md)
    return results


def collect_index_files(root: Path) -> list[Path]:
    """Find slug/index.md leaf posts (depth >= 4 inside blog root).

    The canonical structure is {family}/{platform}/{slug}/index.md, which gives
    rel.parts = (family, platform, slug, 'index.md') — 4 parts total.

    Excluded (depth < 4):
    - root/index.md                     (depth 1)
    - root/{family}/index.md            (depth 2)
    - root/{family}/{platform}/index.md (depth 3 — section landing pages)
    """
    results = []
    for md in root.rglob("index.md"):
        rel = md.relative_to(root)
        # Must be at least family/platform/slug/index.md — 4 parts
        if len(rel.parts) < 4:
            continue
        results.append(md)
    return results


def _check_aliases_for_test_slugs(
    aliases: list, rel: Path, fails: list
) -> None:
    """Append FAIL entries for any alias whose final path segment starts with 'test'."""
    for alias in aliases:
        alias_slug = str(alias).rstrip("/").rsplit("/", 1)[-1]
        if alias_slug.lower().startswith("test"):
            fails.append(
                f"FAIL  [{rel}] alias '{alias}' contains test-named slug "
                f"'{alias_slug}' — remove test artifacts from aliases."
            )


def main() -> int:
    fails = []
    warns = []

    flat_files = collect_flat_english_files(BLOG_CONTENT_ROOT)

    for path in sorted(flat_files):
        stem = path.stem  # e.g. "create-hyperlinks-excel-python"
        rel = path.relative_to(BLOG_CONTENT_ROOT)

        # Check 1: slug derived from test method name
        if stem.lower().startswith("test"):
            fails.append(
                f"FAIL  [{rel}] slug '{stem}' starts with 'test' — "
                "likely derived from an internal test method name, not the content title."
            )

        # Check 2 (P-05): flat file must not exist; all leaf content must use slug/index.md
        fails.append(
            f"FAIL  [{rel}] flat file '{path.name}' must be restructured as "
            f"'{stem}/index.md' — blog posts require directory-based slug structure."
        )

        # Check 3: URL collision — same-name subdirectory with index.md also exists
        subdir_index = path.parent / stem / "index.md"
        if subdir_index.exists():
            warns.append(
                f"WARN  [{rel}] Hugo URL collision: both '{rel}' and "
                f"'{subdir_index.relative_to(BLOG_CONTENT_ROOT)}' target the same URL."
            )

        # Check 4: canonical URL mismatch
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(r"^canonical:\s*(.+)$", content, re.MULTILINE)
        if m:
            canonical = m.group(1).strip()
            expected_suffix = f"/{stem}/"
            if not canonical.endswith(expected_suffix):
                warns.append(
                    f"WARN  [{rel}] canonical '{canonical}' does not end with '{expected_suffix}'"
                )

        # Check 5 (P-06): aliases must not contain test-named slugs
        fm = extract_frontmatter(content)
        aliases = fm.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        _check_aliases_for_test_slugs(aliases, rel, fails)

    # Check all index.md files for aliases with test slugs too (P-06 — directory posts)
    for path in sorted(collect_index_files(BLOG_CONTENT_ROOT)):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = extract_frontmatter(content)
        aliases = fm.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        if not aliases:
            continue
        rel = path.relative_to(BLOG_CONTENT_ROOT)
        _check_aliases_for_test_slugs(aliases, rel, fails)

    for msg in warns:
        print(msg)
    for msg in fails:
        print(msg)

    if fails:
        print(f"\n{len(fails)} FAIL(s), {len(warns)} WARN(s) — slug hygiene check FAILED.")
        return 1

    if warns:
        print(f"\n0 FAILs, {len(warns)} WARN(s) — slug hygiene check passed with warnings.")
    else:
        print("Slug hygiene check PASSED — 0 issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
