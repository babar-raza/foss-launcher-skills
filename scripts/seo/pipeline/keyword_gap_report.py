"""
SEO-KEYWORD-GAP-REPORT keyword_gap_report.py
===============================================
Read-only report: real GSC (Schema B) URLs that Google is tracking real
search impressions for, but that map_url.py cannot resolve to any content
file in this repo -- genuine, real-demand content-gap candidates.

Each candidate is classified:
  structural   -- the URL path is a bare site root or a single-segment
                   family section (e.g. "blog.aspose.org/cells/") that Hugo
                   auto-generates as a list page with no backing markdown
                   file. Not a real content gap -- do not action.
  investigate  -- a real, specific-looking slug with no backing file. Could
                   be a moved/renamed/deleted page needing a redirect, or a
                   genuine content opportunity. Requires a human/agent look,
                   never auto-created.

This module deliberately does not decide what to DO about a gap (write a
redirect, plan new content, etc.) -- see the mission's design summary:
demand proves demand, never truth. It reports evidence for a human/agent
to act on, grounded in real query text and real impressions, never invented.

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = _REPO_ROOT / "reports" / "seo"

try:
    from seo.pipeline.map_url import build_url_map
    from seo.pipeline.keyword_lookup import top_queries_for_url
except ImportError:
    from map_url import build_url_map
    from keyword_lookup import top_queries_for_url


def _classify(gsc_url: str) -> str:
    path = urlparse(gsc_url).path.strip("/")
    segments = [s for s in path.split("/") if s]
    # Root ("") or a single segment (a bare family/section root, e.g.
    # "cells") are exactly the shape of a Hugo auto-generated list page.
    return "structural" if len(segments) <= 1 else "investigate"


def build_gap_report() -> dict:
    result = build_url_map()
    candidates = []
    for entry in result.get("url_map", []):
        if entry.get("content_path") is not None:
            continue
        if entry.get("lang") != "en":
            continue
        gsc_url = entry.get("gsc_url", "")
        queries = top_queries_for_url(gsc_url) or []
        candidates.append({
            "gsc_url": gsc_url,
            "classification": _classify(gsc_url),
            "top_queries": [
                {"query": q.get("query"), "impressions": q.get("impressions", 0)}
                for q in queries
            ],
            "total_impressions": sum(q.get("impressions", 0) for q in queries),
        })

    candidates.sort(key=lambda c: (-c["total_impressions"], c["gsc_url"]))
    investigate = [c for c in candidates if c["classification"] == "investigate"]
    structural = [c for c in candidates if c["classification"] == "structural"]

    return {
        "meta": {
            "generated_by": "keyword_gap_report.py",
            "total_english_gsc_urls": result.get("match_stats", result.get("stats", {})).get("total_gsc_urls"),
            "total_gap_candidates": len(candidates),
            "investigate_count": len(investigate),
            "structural_count": len(structural),
        },
        "investigate": investigate,
        "structural": structural,
    }


def main() -> None:
    report = build_gap_report()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "keyword_gap_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== Keyword Gap Report ===")
    print(f"Total English GSC URLs : {report['meta']['total_english_gsc_urls']}")
    print(f"Gap candidates         : {report['meta']['total_gap_candidates']}")
    print(f"  investigate          : {report['meta']['investigate_count']}")
    print(f"  structural (no-op)   : {report['meta']['structural_count']}")
    print()
    for c in report["investigate"]:
        print(f"  [investigate] {c['gsc_url']} -- {c['total_impressions']} impressions")
        for q in c["top_queries"][:3]:
            print(f"      \"{q['query']}\" ({q['impressions']})")
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
