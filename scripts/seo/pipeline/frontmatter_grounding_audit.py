"""
SEO-KEYWORDS-FRONTMATTER-GROUNDING frontmatter_grounding_audit.py
====================================================================
Read-only report: for every real KB page (the site page_role.py's >=5-
keyword check actually applies to), compute what frontmatter_grounding.py's
three-tier lookup would currently return, and compare it against the page's
EXISTING `keywords:` frontmatter count.

Never writes to any content file -- this is the evaluator-first stage for
keyword grounding, matching the same discipline already applied to titles
(SEO-TITLE-CONSISTENCY-EVALUATOR). An actual content-frontmatter rewrite
based on this report's findings would need to go through the same S-116
governed review path as any other content write in this mission -- not
attempted here.

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_ROOT = _REPO_ROOT / "content"
REPORTS_DIR = _REPO_ROOT / "reports" / "seo"

try:
    from seo.pipeline.frontmatter_grounding import ground_keywords_for_page
    from seo.pipeline.map_url import build_url_map
except ImportError:
    from frontmatter_grounding import ground_keywords_for_page
    from map_url import build_url_map

_url_map_cache: dict[str, str] | None = None


def _content_path_to_gsc_url() -> dict[str, str]:
    global _url_map_cache
    if _url_map_cache is not None:
        return _url_map_cache
    _url_map_cache = {}
    try:
        result = build_url_map()
        for entry in result.get("url_map", []):
            cp, url = entry.get("content_path"), entry.get("gsc_url")
            if cp and url:
                _url_map_cache[cp] = url
    except Exception:
        _url_map_cache = {}
    return _url_map_cache


def _read_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None


def audit_kb_pages(content_root: Path | None = None) -> list[dict]:
    content_root = content_root or CONTENT_ROOT
    root = content_root / "kb.aspose.org" / "en"
    results = []
    if not root.exists():
        return results

    url_map = _content_path_to_gsc_url()

    for path in sorted(root.rglob("*.md")):
        if path.name in ("_index.md",):
            continue
        fm = _read_frontmatter(path)
        if fm is None:
            continue
        try:
            rel = str(path.relative_to(content_root.parent)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")
        parts = path.relative_to(root).parts
        if len(parts) < 2:
            continue
        family, platform = parts[0], parts[1]
        title = fm.get("title") if isinstance(fm.get("title"), str) else None
        description = fm.get("description") if isinstance(fm.get("description"), str) else None
        existing_keywords = fm.get("keywords") if isinstance(fm.get("keywords"), list) else []

        grounded = ground_keywords_for_page(
            family=family, page_title=title or "", description=description,
            gsc_url=url_map.get(rel),
        )
        results.append({
            "path": rel,
            "family": family,
            "platform": platform,
            "existing_keyword_count": len(existing_keywords),
            "meets_min_5_count": len(existing_keywords) >= 5,
            "grounded_keyword_source": grounded["keyword_source"],
            "grounded_keyword_count": len(grounded["keywords"]),
        })
    return results


def build_report() -> dict:
    pages = audit_kb_pages()
    by_source: dict[str, int] = {}
    for p in pages:
        by_source[p["grounded_keyword_source"]] = by_source.get(p["grounded_keyword_source"], 0) + 1

    return {
        "meta": {
            "generated_by": "frontmatter_grounding_audit.py",
            "total_kb_pages": len(pages),
            "by_grounded_source": by_source,
            "pages_meeting_min_5_count": sum(1 for p in pages if p["meets_min_5_count"]),
        },
        "pages": pages,
    }


def main() -> None:
    report = build_report()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "frontmatter_grounding_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    m = report["meta"]
    print("=== Frontmatter Grounding Audit (KB pages, read-only) ===")
    print(f"Total KB pages evaluated : {m['total_kb_pages']}")
    print(f"Pages with >=5 existing keywords: {m['pages_meeting_min_5_count']}")
    print("Grounded keyword_source distribution (what's REALLY available today):")
    for source, count in sorted(m["by_grounded_source"].items(), key=lambda x: -x[1]):
        print(f"  {source:<10} {count}")
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
