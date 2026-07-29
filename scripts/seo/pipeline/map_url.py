"""
SEO-002b map_url.py
====================
For each Schema B GSC URL entry, find the content file that generates it.

URL -> content path convention:
  https://blog.aspose.org/3d/python/my-post/  ->  content/blog.aspose.org/3d/python/my-post/index.md
  https://docs.aspose.org/en/3d/python/page/  ->  content/docs.aspose.org/en/3d/python/page/index.md
  https://products.aspose.org/3d/             ->  content/products.aspose.org/en/3d/_index.md

Reads Schema B keyword files directly (calls validate inline).
Appends 'url_map' + 'match_stats' to reports/seo/page_index.json.

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from seo.pipeline.schema import classify_keyword_file, SCHEMA_B
except ImportError:
    from schema import classify_keyword_file, SCHEMA_B

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_ROOT = REPO_ROOT / "content"
KEYWORDS_DIR = REPO_ROOT / "keywords"
REPORTS_DIR = REPO_ROOT / "reports" / "seo"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Schema classification is structural (see schema.py::classify_keyword_file),
# not a filename allowlist. A filename list previously covered only 4 of the
# 7 real Schema B files (missing docs, blog, kb), silently dropping their
# GSC data from the url_map.

# ---------------------------------------------------------------------------
# Load Schema B entries directly from keywords/
# ---------------------------------------------------------------------------


def _load_schema_b_entries(keywords_dir: Path) -> list[dict]:
    """Return all Schema B entries from keywords/ as raw dicts.

    Walks every *.json file in keywords_dir and classifies each one
    structurally rather than matching against a fixed filename list.
    """
    entries: list[dict] = []
    for path in sorted(keywords_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.warn(f"map_url.py: could not parse {path.name}: {exc}")
            continue
        if classify_keyword_file(raw) != SCHEMA_B:
            continue
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and "url" in entry:
                    entry["_source_file"] = path.name
                    entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# URL -> content path resolution
# ---------------------------------------------------------------------------


def _resolve_url_to_content_path(url: str, content_root: Path) -> tuple[Path | None, str]:
    """
    Attempt to map a GSC URL to a content file.

    Returns (path_or_None, match_type) where match_type is one of:
      'exact'       — found via primary strategy
      'alt_index'   — found via _index.md fallback
      'bare_file'   — found via bare .md fallback
      'unmatched'   — not found
    """
    parsed = urlparse(url)
    domain = parsed.netloc  # e.g. 'blog.aspose.org'
    path_str = parsed.path  # e.g. '/3d/python/my-post/'

    # Normalise: ensure trailing slash removed for path joining, keep it for products
    path_str = path_str or "/"

    # Strip leading slash
    stripped = path_str.lstrip("/")

    site_root = content_root / domain

    if not site_root.exists():
        return None, "unmatched"

    # Strategy 1: {domain}/{path}/index.md
    candidate1 = site_root / stripped / "index.md" if stripped else site_root / "index.md"
    if candidate1.exists():
        return candidate1, "exact"

    # Strategy 2: {domain}/{path}/_index.md
    candidate2 = site_root / stripped / "_index.md" if stripped else site_root / "_index.md"
    if candidate2.exists():
        return candidate2, "alt_index"

    # Strategy 3: products.aspose.org and websites.aspose.org use /en/ prefix in
    # content (Finding #45: websites.aspose.org was missing from every /en/-prefix
    # strategy, so real, existing content -- e.g.
    # content/websites.aspose.org/en/aspose/app/_index.md -- misreported as an
    # "unmatched"/content-gap candidate when it demonstrably already exists).
    # e.g. https://products.aspose.org/3d/ -> content/products.aspose.org/en/3d/_index.md
    #      https://websites.aspose.org/aspose/app/ -> content/websites.aspose.org/en/aspose/app/_index.md
    if domain in ("products.aspose.org", "websites.aspose.org"):
        candidate3 = site_root / "en" / stripped / "_index.md" if stripped else site_root / "en" / "_index.md"
        if candidate3.exists():
            return candidate3, "exact"
        candidate3b = site_root / "en" / stripped / "index.md" if stripped else site_root / "en" / "index.md"
        if candidate3b.exists():
            return candidate3b, "exact"

    # Strategy 4: docs/kb/reference use /en/ prefix in content
    if domain in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
        # The URL path typically does NOT include /en/ but content path does
        # e.g. /3d/python/page/ -> content/docs.aspose.org/en/3d/python/page/index.md
        # But URL may already include /en/ — normalise
        if stripped.startswith("en/"):
            inner = stripped[3:]
        else:
            inner = stripped
        candidate4 = site_root / "en" / inner / "index.md" if inner else site_root / "en" / "index.md"
        if candidate4.exists():
            return candidate4, "exact"
        candidate4b = site_root / "en" / inner / "_index.md" if inner else site_root / "en" / "_index.md"
        if candidate4b.exists():
            return candidate4b, "alt_index"

    # Strategy 5: bare .md file (non-directory URL)
    # e.g. /some/page -> content/{domain}/some/page.md
    if stripped:
        candidate5 = site_root / (stripped.rstrip("/") + ".md")
        if candidate5.exists():
            return candidate5, "bare_file"

        # Strategy 5b: docs/kb/reference use /en/ prefix in content, same as Strategy 4 —
        # but Strategy 4 only tries index.md/_index.md forms, never a bare .md file.
        # e.g. https://docs.aspose.org/words/python/getting-started/installation/ ->
        #      content/docs.aspose.org/en/words/python/getting-started/installation.md
        if domain in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
            inner = stripped[3:] if stripped.startswith("en/") else stripped
            candidate5b = site_root / "en" / (inner.rstrip("/") + ".md")
            if candidate5b.exists():
                return candidate5b, "bare_file"

    return None, "unmatched"


# ---------------------------------------------------------------------------
# Build url_map
# ---------------------------------------------------------------------------


def build_url_map(
    keywords_dir: Path | None = None,
    content_root: Path | None = None,
) -> dict:
    """
    Build the url_map from Schema B keyword entries.

    Returns:
        {
          "url_map": [...],
          "match_stats": {...}
        }
    """
    if keywords_dir is None:
        keywords_dir = KEYWORDS_DIR
    if content_root is None:
        content_root = CONTENT_ROOT

    entries = _load_schema_b_entries(keywords_dir)

    url_map: list[dict] = []
    matched = 0
    unmatched_list: list[str] = []

    for entry in entries:
        url = entry.get("url", "")
        lang = entry.get("lang", "en")
        source_file = entry.get("_source_file", "")

        if not url.startswith("https://"):
            url_map.append({
                "gsc_url": url,
                "content_path": None,
                "match_type": "unmatched",
                "lang": lang,
                "matched": False,
                "source_file": source_file,
                "note": "URL does not start with https://",
            })
            unmatched_list.append(url)
            continue

        content_path, match_type = _resolve_url_to_content_path(url, content_root)

        if content_path is not None:
            rel_path = str(content_path.relative_to(REPO_ROOT)).replace("\\", "/")
            url_map.append({
                "gsc_url": url,
                "content_path": rel_path,
                "match_type": match_type,
                "lang": lang,
                "matched": True,
                "source_file": source_file,
            })
            matched += 1
        else:
            url_map.append({
                "gsc_url": url,
                "content_path": None,
                "match_type": "unmatched",
                "lang": lang,
                "matched": False,
                "source_file": source_file,
            })
            unmatched_list.append(url)

    total = len(url_map)
    unmatched_count = total - matched
    match_rate = round(matched / total, 4) if total > 0 else 0.0

    return {
        "url_map": url_map,
        "match_stats": {
            "total_gsc_urls": total,
            "matched": matched,
            "unmatched": unmatched_count,
            "match_rate": match_rate,
        },
        "_unmatched_urls": unmatched_list,
    }


# ---------------------------------------------------------------------------
# Append to page_index.json
# ---------------------------------------------------------------------------


def append_url_map_to_page_index(
    url_map_result: dict,
    page_index_path: Path | None = None,
) -> Path:
    """Load page_index.json, append url_map section, write back."""
    if page_index_path is None:
        page_index_path = REPORTS_DIR / "page_index.json"

    if page_index_path.exists():
        doc = json.loads(page_index_path.read_text(encoding="utf-8"))
    else:
        doc = {"meta": {}, "pages": []}

    doc["url_map"] = url_map_result["url_map"]
    doc["match_stats"] = url_map_result["match_stats"]

    page_index_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return page_index_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== SEO URL Mapper ===")
    result = build_url_map()
    stats = result["match_stats"]

    print(f"Total GSC URLs       : {stats['total_gsc_urls']}")
    print(f"  Matched            : {stats['matched']}")
    print(f"  Unmatched          : {stats['unmatched']}")
    print(f"  Match rate         : {stats['match_rate']:.1%}")
    print()

    unmatched = result.get("_unmatched_urls", [])
    if unmatched:
        print(f"Unmatched URLs ({len(unmatched)}):")
        for u in unmatched[:30]:
            print(f"  {u}")
        if len(unmatched) > 30:
            print(f"  ... and {len(unmatched) - 30} more")

    out_path = append_url_map_to_page_index(result)
    print(f"\nurl_map appended to  : {out_path}")


if __name__ == "__main__":
    main()
