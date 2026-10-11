"""
SEO-002a inventory.py
======================
Walk all primary content files across the Hugo multi-site monorepo and
extract SEO frontmatter state per page.

Primary files:
  - index.md  (directory-based posts)
  - _index.md (Hugo section indices)
  - top-level *.md that are NOT locale variants
    (i.e. NOT matching *.{2-letter-lang}.md pattern)

Locale variants (e.g. index.ar.md, index.bg.md) are skipped.

Output: reports/seo/page_index.json

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("inventory.py requires PyYAML: pip install pyyaml")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_ROOT = REPO_ROOT / "content"
REPORTS_DIR = REPO_ROOT / "reports" / "seo"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Regex: matches locale variant suffix like .ar.md, .bg.md, .zh.md
# Also matches _index locale variants that some sites use: _index.ar.md
_LOCALE_VARIANT_RE = re.compile(r"\.[a-z]{2}\.md$", re.IGNORECASE)

# Hugo path separators & site roots
_SITES = [
    "blog.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
    "websites.aspose.org",
    "www.aspose.org",
]

# page_role values that should be skipped
_SKIP_ROLES = {"toc", "archive", "search", "navigation"}

# Products site uses different frontmatter keys
_PRODUCTS_SITE = "products.aspose.org"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_primary_file(path: Path) -> bool:
    """Return True if path is a primary (non-locale-variant) content file."""
    name = path.name
    if _LOCALE_VARIANT_RE.search(name):
        return False
    if name.endswith(".md"):
        return True
    return False


def _extract_frontmatter(text: str) -> dict | None:
    """Parse YAML frontmatter delimited by --- lines. Returns None on failure."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None


def _get_site_from_path(path: Path) -> str:
    """Extract site name from content path."""
    try:
        rel = path.relative_to(CONTENT_ROOT)
        return rel.parts[0]
    except ValueError:
        return "unknown"


def _get_family_platform_from_path(path: Path, site: str) -> tuple[str | None, str | None]:
    """
    Extract family and platform from content path.

    blog.aspose.org:    content/blog.aspose.org/{family}/{platform}/...
    docs.aspose.org:    content/docs.aspose.org/en/{family}/{platform}/...
    kb.aspose.org:      content/kb.aspose.org/en/{family}/{platform}/...
    products.aspose.org:content/products.aspose.org/en/{family}/...
    reference.aspose.org:content/reference.aspose.org/en/{family}/{platform}/...
    websites.aspose.org:content/websites.aspose.org/{slug}/...  (no family/platform concept)
    www.aspose.org:     content/www.aspose.org/...
    """
    try:
        rel = path.relative_to(CONTENT_ROOT / site)
    except ValueError:
        return None, None

    parts = rel.parts

    # docs, kb, reference: parts[0] = lang code (e.g. 'en'), parts[1] = family, parts[2] = platform
    # products: parts[0] = lang code, parts[1] = family
    # blog: parts[0] = family, parts[1] = platform

    if site in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
        family = parts[1] if len(parts) > 1 else None
        platform = parts[2] if len(parts) > 2 else None
        return family, platform

    if site == "products.aspose.org":
        family = parts[1] if len(parts) > 1 else None
        return family, None

    if site == "blog.aspose.org":
        family = parts[0] if len(parts) > 0 else None
        platform = parts[1] if len(parts) > 1 else None
        return family, platform

    return None, None


def _build_page_record(path: Path, fm: dict, site: str) -> dict | None:
    """Build a page record from frontmatter. Returns None if the page should be skipped."""
    page_role = fm.get("page_role") or fm.get("layout") or None

    # Skip utility pages
    if isinstance(page_role, str) and page_role.lower() in _SKIP_ROLES:
        return None
    # Also skip by layout for common utility layouts
    layout = fm.get("layout", "")
    if isinstance(layout, str) and layout.lower() in ("archives", "search", "navigation"):
        return None

    family, platform = _get_family_platform_from_path(path, site)

    is_products = site == _PRODUCTS_SITE

    if is_products:
        seo_title = fm.get("head_title") or fm.get("seoTitle") or fm.get("title") or None
        description = fm.get("head_description") or fm.get("description") or None
        site_schema = "products"
    else:
        seo_title = fm.get("seoTitle") or fm.get("seo_title") or None
        description = fm.get("description") or None
        site_schema = "standard"

    raw_tags = fm.get("tags") or []
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags = [t for t in raw_tags if isinstance(t, str)]

    seo_title_str = seo_title or ""
    description_str = description or ""

    rel_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")

    return {
        "path": rel_path,
        "site": site,
        "family": family,
        "platform": platform,
        "page_role": page_role if isinstance(page_role, str) else None,
        "seo_title": seo_title_str if seo_title_str else None,
        "description": description_str if description_str else None,
        "tags": tags,
        "url": fm.get("url") or None,
        "seo_fields": {
            "has_seo_title": bool(seo_title_str),
            "has_description": bool(description_str),
            "has_tags": len(tags) > 0,
            "seo_title_len": len(seo_title_str),
            "description_len": len(description_str),
            "tag_count": len(tags),
        },
        "site_schema": site_schema,
    }


# ---------------------------------------------------------------------------
# Core walker
# ---------------------------------------------------------------------------


def build_inventory(content_root: Path | None = None) -> list[dict]:
    """
    Walk content tree and return a list of page records.
    Malformed YAML files are skipped with a warning.
    """
    if content_root is None:
        content_root = CONTENT_ROOT

    pages: list[dict] = []
    parse_errors: list[str] = []

    for site in _SITES:
        site_root = content_root / site
        if not site_root.exists():
            continue

        for path in sorted(site_root.rglob("*.md")):
            if not _is_primary_file(path):
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                warnings.warn(f"inventory.py: cannot read {path}: {exc}")
                continue

            fm = _extract_frontmatter(text)
            if fm is None:
                parse_errors.append(str(path))
                warnings.warn(f"inventory.py: malformed YAML in {path}, skipping")
                continue

            record = _build_page_record(path, fm, site)
            if record is None:
                continue  # skipped utility page

            pages.append(record)

    return pages


# ---------------------------------------------------------------------------
# Stats helpers (used by CLI and map_url.py)
# ---------------------------------------------------------------------------


def _compute_seo_stats(pages: list[dict]) -> dict:
    total = len(pages)
    has_seo_title = sum(1 for p in pages if p["seo_fields"]["has_seo_title"])
    has_description = sum(1 for p in pages if p["seo_fields"]["has_description"])
    has_tags = sum(1 for p in pages if p["seo_fields"]["has_tags"])
    return {
        "total_pages": total,
        "has_seo_title": has_seo_title,
        "has_description": has_description,
        "has_tags": has_tags,
        "missing_seo_title": total - has_seo_title,
        "missing_description": total - has_description,
        "missing_tags": total - has_tags,
    }


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------


def write_page_index(pages: list[dict], output_path: Path | None = None) -> Path:
    """Write page_index.json (pages list + seo_stats). Returns the path written."""
    if output_path is None:
        output_path = REPORTS_DIR / "page_index.json"

    stats = _compute_seo_stats(pages)
    doc = {
        "meta": {
            "generated_by": "inventory.py",
            "total_pages": stats["total_pages"],
            "seo_stats": stats,
        },
        "pages": pages,
    }
    output_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== SEO Inventory Builder ===")
    print(f"Content root : {CONTENT_ROOT}")
    pages = build_inventory()
    stats = _compute_seo_stats(pages)
    out_path = write_page_index(pages)

    print(f"Pages indexed        : {stats['total_pages']}")
    print(f"  has seoTitle       : {stats['has_seo_title']}")
    print(f"  has description    : {stats['has_description']}")
    print(f"  has tags           : {stats['has_tags']}")
    print(f"  missing seoTitle   : {stats['missing_seo_title']}")
    print(f"  missing description: {stats['missing_description']}")
    print()

    # Per-site breakdown
    site_counts: dict[str, int] = {}
    for p in pages:
        site_counts[p["site"]] = site_counts.get(p["site"], 0) + 1
    print("Pages per site:")
    for site, count in sorted(site_counts.items()):
        print(f"  {site:<30} {count:>6}")

    print(f"\npage_index.json written to: {out_path}")


if __name__ == "__main__":
    main()
