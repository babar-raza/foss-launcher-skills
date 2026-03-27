"""
SEO-004 analyze.py
===================
Opportunity scoring module. For each page that has either a URL match from
map_url.py or a high-confidence Schema A keyword match, produce an opportunity
record with a score, reasoning, and the specific gaps found.

Two analysis paths:
  Path A — With GSC metrics (queries[] present and non-empty): metrics-first.
  Path B — Without metrics (metrics_missing or no url_map match for Schema B):
            structural-only.

No LLM calls. No network calls. stdlib + pathlib only.

Outputs:
  reports/seo/opportunities.json   — per-page opportunity records
  reports/seo/seo_gap_summary.json — inventory-level gap statistics
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — ensure sibling pipeline modules are importable regardless of
# how the script is invoked (e.g. `python scripts/seo/pipeline/analyze.py`
# from repo root, or via `python -m scripts.seo.pipeline.analyze`).
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_PIPELINE_DIR = _THIS_FILE.parent          # scripts/seo/pipeline/
_REPO_ROOT = _THIS_FILE.parents[3]         # .../aspose.org

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Local imports (after sys.path is fixed)
# ---------------------------------------------------------------------------

try:
    from scripts.seo.pipeline.validate import run_validation  # type: ignore
except ImportError as exc:
    sys.exit(
        f"analyze.py: cannot import validate.py — {exc}\n"
        "Run from repo root: python scripts/seo/pipeline/analyze.py"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = _REPO_ROOT / "reports" / "seo"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PAGE_INDEX_PATH = REPORTS_DIR / "page_index.json"
OPPORTUNITIES_PATH = REPORTS_DIR / "opportunities.json"
GAP_SUMMARY_PATH = REPORTS_DIR / "seo_gap_summary.json"

# Impression threshold for noise filter
_IMPRESSION_THRESHOLD = 10
# CTR gap: high impressions but very low CTR — thresholds for HIGH opportunity classification.
# With full GSC coverage (Phase 0a complete for docs/blog/kb/reference), pages in the
# 100+ impressions range will qualify for HIGH. Before Phase 0a, only 3.4% of pages had
# GSC data, making HIGH=0 the expected outcome. Now that all 7 subdomains are connected,
# HIGH opportunities will surface once the weekly gsc-query-collector workflow deposits
# fresh CSV exports into reports/gsc/.
_CTR_GAP_MIN_IMPRESSIONS = 100
_CTR_GAP_MAX_CTR = 0.02
# High-impression threshold for tag gap check
_TAG_GAP_IMPRESSION_MIN = 50
# Description length bounds
_DESC_SHORT = 130
_DESC_LONG = 160
# page_role values that are always SKIP
_SKIP_ROLES = {"toc", "archive", "search", "navigation"}

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric token split — re.findall(r'[a-z0-9]+', text.lower())."""
    if not text:
        return []
    return re.findall(r"[a-z0-9]+", text.lower())


def _query_tokens_in_title(query_str: str, title_tokens: list[str]) -> bool:
    """Return True if ANY token from query_str appears in title_tokens."""
    for tok in _tokenize(query_str):
        if tok in title_tokens:
            return True
    return False


def _query_tokens_in_tags(query_str: str, tag_token_set: set[str]) -> bool:
    """Return True if ANY token from query_str appears in tag_token_set."""
    for tok in _tokenize(query_str):
        if tok in tag_token_set:
            return True
    return False


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _position_zone(avg_position: float) -> str:
    if avg_position < 5:
        return "winning"
    if avg_position <= 20:
        return "opportunity"
    if avg_position <= 30:
        return "low_priority"
    return "content_gap"


def _score_path_a(
    *,
    ctr_gap: bool,
    position_zone: str,
    title_aligned: bool,
    description_ok: bool,
    tag_gap_count: int,
    page_role: str | None,
    has_seo_title: bool,
    has_description: bool,
    has_tags: bool,
    all_queries_below_threshold: bool,
) -> tuple[str, str]:
    """Return (opportunity_level, score_reason) for Path A (metrics-present)."""

    # Hard SKIPs first
    if all_queries_below_threshold:
        return "SKIP", "all_queries_below_threshold"

    if isinstance(page_role, str) and page_role.lower() in _SKIP_ROLES:
        return "SKIP", f"page_role={page_role} is a utility page"

    if not has_seo_title and not has_description and not has_tags:
        return "SKIP", "no seo_title, description, or tags present"

    # HIGH
    if ctr_gap and position_zone == "opportunity" and not title_aligned:
        return "HIGH", "high impressions low CTR, in opportunity zone, title not aligned"

    # MEDIUM
    if position_zone == "opportunity" and (not description_ok or tag_gap_count >= 2):
        reason_parts = []
        if not description_ok:
            reason_parts.append("description out-of-range")
        if tag_gap_count >= 2:
            reason_parts.append(f"tag_gap_count={tag_gap_count}")
        return "MEDIUM", "in opportunity zone: " + ", ".join(reason_parts)

    # LOW
    if tag_gap_count >= 1:
        return "LOW", f"tag_gap_count={tag_gap_count} with no major position signal"
    if position_zone == "winning" and (not title_aligned or not description_ok):
        return "LOW", "winning position but minor title/description gap"

    # Catch-all SKIP
    if position_zone in ("winning", "content_gap"):
        return "SKIP", f"position_zone={position_zone} with no actionable gaps"
    return "SKIP", "no significant gaps detected"


def _score_path_b(
    *,
    title_aligned: bool,
    description_ok: bool,
    description_len: int,
    has_seo_title: bool,
    page_role: str | None,
    has_tags: bool,
) -> tuple[str, str]:
    """Return (opportunity_level, score_reason) for Path B (structural-only)."""

    if isinstance(page_role, str) and page_role.lower() in _SKIP_ROLES:
        return "SKIP", f"page_role={page_role} is a utility page"

    # MEDIUM: title exists but misaligned with keywords
    if not title_aligned and has_seo_title:
        return "MEDIUM", "seo_title present but not aligned with target keywords"

    # LOW: description out-of-range
    if not description_ok:
        if description_len < _DESC_SHORT:
            return "LOW", f"description too short ({description_len} chars, min {_DESC_SHORT})"
        return "LOW", f"description too long ({description_len} chars, max {_DESC_LONG})"

    # LOW: missing seo_title entirely (no traffic data to confirm severity)
    if not has_seo_title:
        return "LOW", "seo_title missing (no GSC data to assess traffic impact)"

    return "SKIP", "structural fields look adequate"


# ---------------------------------------------------------------------------
# Build keyword lookup structures
# ---------------------------------------------------------------------------


def _build_schema_a_index(
    schema_a_records: list[dict],
) -> dict[str, dict[str, list[str]]]:
    """
    Build a {family: {pageTitle_lower: [keywords]}} index from Schema A records.
    Keyed by family so that keyword matching is always family-scoped — pages from
    the 'cells' family only match against 'cells' Schema A records, never against
    'page', 'pdf', or any other family's records.
    """
    index: dict[str, dict[str, list[str]]] = {}
    for rec in schema_a_records:
        family = rec.get("family") or ""
        title_lower = rec.get("pageTitle", "").lower().strip()
        if title_lower:
            index.setdefault(family, {})[title_lower] = rec.get("keywords", [])
    return index


def _match_schema_a_keywords(
    seo_title: str | None,
    schema_a_index: dict[str, dict[str, list[str]]],
    family: str | None = None,
) -> list[str]:
    """
    Find Schema A keywords that approximately match a page's seo_title.
    Only searches records belonging to the same *family* as the page.
    Strategy: token-overlap heuristic — at least 2 shared tokens required.
    Returns matched keyword list (may be empty).
    """
    if not seo_title:
        return []
    # Restrict to the family's sub-index; fall back to empty dict if unknown
    family_index = schema_a_index.get(family or "", {})
    if not family_index:
        return []
    title_lower = seo_title.lower().strip()
    title_toks = set(_tokenize(title_lower))
    best_overlap = 0
    best_kws: list[str] = []
    for page_title_lower, kws in family_index.items():
        pt_toks = set(_tokenize(page_title_lower))
        if not pt_toks:
            continue
        overlap = len(title_toks & pt_toks)
        if overlap > best_overlap:
            best_overlap = overlap
            best_kws = kws
    # Only use if at least 2 shared tokens (avoids spurious matches)
    if best_overlap >= 2:
        return best_kws
    return []


# ---------------------------------------------------------------------------
# Per-page analysis
# ---------------------------------------------------------------------------


def _analyze_page_path_a(
    page: dict,
    gsc_entry: dict,
) -> dict:
    """
    Analyze a page that has a matched GSC entry (Path A).
    gsc_entry is the full Schema B record (url, keywords, queries?, metrics_missing).
    """
    queries_raw: list[dict] = gsc_entry.get("queries", [])
    metrics_missing: bool = gsc_entry.get("metrics_missing", True)

    # If metrics actually missing despite being "matched", fall back to Path B
    if metrics_missing or not queries_raw:
        # Use Schema B keywords as the query set for structural analysis
        keywords = gsc_entry.get("keywords", [])
        return _analyze_page_path_b(page, keywords)

    # Step 1 — Noise filter
    filtered_queries = [q for q in queries_raw if q.get("impressions", 0) >= _IMPRESSION_THRESHOLD]
    all_below_threshold = len(filtered_queries) == 0

    # Step 2 — Primary intent
    if filtered_queries:
        sorted_q = sorted(filtered_queries, key=lambda q: q.get("impressions", 0), reverse=True)
        primary_q = sorted_q[0]
        top3 = sorted_q[:3]
    else:
        primary_q = {}
        top3 = []

    primary_query_str = primary_q.get("query") if primary_q else None
    primary_impressions = primary_q.get("impressions") if primary_q else None
    primary_ctr = primary_q.get("ctr") if primary_q else None
    primary_position = primary_q.get("position") if primary_q else None

    # Step 3 — CTR gap
    if primary_q and not all_below_threshold:
        imp = primary_q.get("impressions", 0)
        ctr = float(primary_q.get("ctr", 1.0))
        ctr_gap = imp > _CTR_GAP_MIN_IMPRESSIONS and ctr < _CTR_GAP_MAX_CTR
    else:
        ctr_gap = False

    # Step 4 — Position zone
    if primary_q and not all_below_threshold:
        pos = float(primary_q.get("position", 100))
        pzone = _position_zone(pos)
    else:
        pzone = "unknown"

    # Step 5 — Title alignment (against top-3 query strings)
    seo_title = page.get("seo_title") or ""
    title_tokens = _tokenize(seo_title)
    if top3 and seo_title:
        title_aligned = any(_query_tokens_in_title(q.get("query", ""), title_tokens) for q in top3)
    else:
        title_aligned = False

    # Step 6 — Description check
    desc = page.get("description") or ""
    desc_len = len(desc)
    description_short = desc_len < _DESC_SHORT
    description_long = desc_len > _DESC_LONG
    description_ok = not description_short and not description_long

    # Step 7 — Tag gap
    tags = page.get("tags") or []
    tag_token_set: set[str] = set()
    for tag in tags:
        tag_token_set.update(_tokenize(tag))

    high_imp_queries = [q for q in filtered_queries if q.get("impressions", 0) >= _TAG_GAP_IMPRESSION_MIN]
    tag_gap_count = sum(
        1 for q in high_imp_queries
        if not _query_tokens_in_tags(q.get("query", ""), tag_token_set)
    )

    # Step 8 — Score
    has_seo_title = bool(seo_title)
    has_description = bool(desc)
    has_tags = len(tags) > 0

    level, reason = _score_path_a(
        ctr_gap=ctr_gap,
        position_zone=pzone,
        title_aligned=title_aligned,
        description_ok=description_ok,
        tag_gap_count=tag_gap_count,
        page_role=page.get("page_role"),
        has_seo_title=has_seo_title,
        has_description=has_description,
        has_tags=has_tags,
        all_queries_below_threshold=all_below_threshold,
    )

    # Matched keywords = query strings from filtered_queries
    matched_kws = [q.get("query", "") for q in filtered_queries]

    return {
        "page_path": page["path"],
        "site": page.get("site"),
        "family": page.get("family"),
        "platform": page.get("platform"),
        "page_role": page.get("page_role"),
        "analysis_path": "metrics",
        "opportunity_level": level,
        "score_reason": reason,
        "signals": {
            "position_zone": pzone,
            "ctr_gap": ctr_gap,
            "title_aligned": title_aligned,
            "description_ok": description_ok,
            "description_len": desc_len,
            "tag_gap_count": tag_gap_count,
            "primary_query": primary_query_str,
            "primary_impressions": primary_impressions,
            "primary_ctr": primary_ctr,
            "primary_position": primary_position,
            "matched_keywords": matched_kws,
        },
        "seo_fields": {
            "seo_title": seo_title if seo_title else None,
            "description": desc if desc else None,
            "tags": tags,
        },
    }


def _analyze_page_path_b(
    page: dict,
    keywords: list[str],
) -> dict:
    """
    Analyze a page with no GSC metrics (Path B — structural-only).
    keywords: the keyword list to use as the query set (Schema B keywords[] or Schema A keywords).
    """
    seo_title = page.get("seo_title") or ""
    desc = page.get("description") or ""
    tags = page.get("tags") or []
    has_seo_title = bool(seo_title)
    desc_len = len(desc)

    # Title alignment: check if any keyword string shares a token with seo_title
    title_tokens = _tokenize(seo_title)
    if keywords and seo_title:
        title_aligned = any(_query_tokens_in_title(kw, title_tokens) for kw in keywords)
    else:
        title_aligned = False

    # Description check
    description_short = desc_len < _DESC_SHORT
    description_long = desc_len > _DESC_LONG
    description_ok = not description_short and not description_long

    # Score
    level, reason = _score_path_b(
        title_aligned=title_aligned,
        description_ok=description_ok,
        description_len=desc_len,
        has_seo_title=has_seo_title,
        page_role=page.get("page_role"),
        has_tags=len(tags) > 0,
    )

    return {
        "page_path": page["path"],
        "site": page.get("site"),
        "family": page.get("family"),
        "platform": page.get("platform"),
        "page_role": page.get("page_role"),
        "analysis_path": "structural",
        "opportunity_level": level,
        "score_reason": reason,
        "signals": {
            "position_zone": "unknown",
            "ctr_gap": False,
            "title_aligned": title_aligned,
            "description_ok": description_ok,
            "description_len": desc_len,
            "tag_gap_count": 0,
            "primary_query": None,
            "primary_impressions": None,
            "primary_ctr": None,
            "primary_position": None,
            "matched_keywords": keywords[:10],  # cap for readability
        },
        "seo_fields": {
            "seo_title": seo_title if seo_title else None,
            "description": desc if desc else None,
            "tags": tags,
        },
    }


# ---------------------------------------------------------------------------
# Build keyword lookup from Schema B url_map entries
# ---------------------------------------------------------------------------


def _build_schema_b_lookup(
    url_map: list[dict],
    schema_b_records: list[dict],
) -> dict[str, dict]:
    """
    Build a {content_path: schema_b_entry} mapping for all matched url_map entries.
    The schema_b_entry is enriched with 'keywords' from the keywords/ file.
    """
    # Build a url -> schema_b_record lookup from validated records
    url_to_record: dict[str, dict] = {}
    for rec in schema_b_records:
        url = rec.get("url", "")
        if url:
            url_to_record[url] = rec

    lookup: dict[str, dict] = {}
    for entry in url_map:
        if not entry.get("matched"):
            continue
        content_path = entry.get("content_path")
        gsc_url = entry.get("gsc_url", "")
        if not content_path:
            continue
        # Merge url_map entry with the full record from schema_b_records
        if gsc_url in url_to_record:
            lookup[content_path] = url_to_record[gsc_url]
        else:
            # Fallback: use the url_map entry itself (no keywords)
            lookup[content_path] = {
                "url": gsc_url,
                "keywords": [],
                "metrics_missing": True,
            }
    return lookup


# ---------------------------------------------------------------------------
# Main analysis orchestrator
# ---------------------------------------------------------------------------


def run_analysis(
    page_index_path: Path | None = None,
) -> dict:
    """
    Run the full opportunity analysis.

    Returns:
        {
            "opportunities": [...],
            "summary": {...},
            "total_pages_analyzed": int,
        }
    Side effects: writes opportunities.json and seo_gap_summary.json.
    """
    if page_index_path is None:
        page_index_path = PAGE_INDEX_PATH

    # ------------------------------------------------------------------
    # 1. Load page_index.json
    # ------------------------------------------------------------------
    if not page_index_path.exists():
        print(f"ERROR: page_index.json not found at {page_index_path}", file=sys.stderr)
        print("Run inventory.py and map_url.py first.", file=sys.stderr)
        sys.exit(1)

    doc = json.loads(page_index_path.read_text(encoding="utf-8"))
    pages: list[dict] = doc.get("pages", [])
    url_map: list[dict] = doc.get("url_map", [])

    if not pages:
        print("WARNING: page_index.json has no pages", file=sys.stderr)

    # ------------------------------------------------------------------
    # 2. Load keyword data (calls validate.py — no LLM, deterministic)
    # ------------------------------------------------------------------
    print("Loading keyword data via validate.py ...")
    kw_result = run_validation()
    schema_b_records: list[dict] = kw_result.get("schema_b", [])
    schema_a_records: list[dict] = kw_result.get("schema_a", [])
    print(f"  Schema B records : {len(schema_b_records)}")
    print(f"  Schema A records : {len(schema_a_records)}")

    # ------------------------------------------------------------------
    # 3. Build lookup structures
    # ------------------------------------------------------------------
    schema_b_by_path = _build_schema_b_lookup(url_map, schema_b_records)
    schema_a_index = _build_schema_a_index(schema_a_records)

    # Build a page dict keyed by path for fast lookup
    pages_by_path: dict[str, dict] = {p["path"]: p for p in pages}

    # ------------------------------------------------------------------
    # 4. Determine analysis set:
    #    (a) pages with a url_map match (Path A if has queries, else Path B)
    #    (b) pages matched via Schema A approximate title matching
    #    Avoid duplicates — url_map matches take precedence.
    # ------------------------------------------------------------------
    analyzed_paths: set[str] = set()
    opportunities: list[dict] = []

    # 4a — url_map matched pages (Schema B)
    for content_path, gsc_entry in schema_b_by_path.items():
        page = pages_by_path.get(content_path)
        if page is None:
            # url_map points to a file not in page_index (utility page or
            # missing from index) — build a minimal stub
            page = {
                "path": content_path,
                "site": content_path.split("/")[1] if "/" in content_path else "unknown",
                "family": None,
                "platform": None,
                "page_role": None,
                "seo_title": None,
                "description": None,
                "tags": [],
                "seo_fields": {
                    "has_seo_title": False,
                    "has_description": False,
                    "has_tags": False,
                    "seo_title_len": 0,
                    "description_len": 0,
                    "tag_count": 0,
                },
            }
        record = _analyze_page_path_a(page, gsc_entry)
        opportunities.append(record)
        analyzed_paths.add(content_path)

    # 4b — Schema A matches for pages NOT already covered by url_map
    # We limit to the first 500 pages for performance (grows with Phase 0a data)
    schema_a_candidates = [p for p in pages if p["path"] not in analyzed_paths]
    matched_via_schema_a = 0
    for page in schema_a_candidates:
        kws = _match_schema_a_keywords(page.get("seo_title"), schema_a_index, family=page.get("family"))
        if not kws:
            continue  # no keyword signal — skip
        record = _analyze_page_path_b(page, kws)
        opportunities.append(record)
        analyzed_paths.add(page["path"])
        matched_via_schema_a += 1

    # ------------------------------------------------------------------
    # 5. Compute summary
    # ------------------------------------------------------------------
    level_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "SKIP": 0}
    for opp in opportunities:
        lvl = opp.get("opportunity_level", "SKIP")
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    total_analyzed = len(opportunities)

    result = {
        "run_at": date.today().isoformat(),
        "total_pages_analyzed": total_analyzed,
        "schema_b_matches": len(schema_b_by_path),
        "schema_a_matches": matched_via_schema_a,
        "summary": level_counts,
        "opportunities": opportunities,
    }

    # ------------------------------------------------------------------
    # 6. Write opportunities.json
    # ------------------------------------------------------------------
    OPPORTUNITIES_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # 7. Write seo_gap_summary.json (pure inventory report from page_index)
    # ------------------------------------------------------------------
    _write_gap_summary(pages, doc.get("meta", {}))

    return result


# ---------------------------------------------------------------------------
# SEO Gap Summary (inventory-only, no LLM)
# ---------------------------------------------------------------------------


def _write_gap_summary(pages: list[dict], meta: dict) -> None:
    """
    Build and write seo_gap_summary.json from page_index data alone.
    Pure inventory report — counts missing fields by site.
    """
    total = len(pages)
    missing_seo_title = sum(1 for p in pages if not p.get("seo_title"))
    missing_description = sum(1 for p in pages if not p.get("description"))
    missing_tags = sum(1 for p in pages if not p.get("tags"))

    # Per-site breakdown
    sites: dict[str, dict] = {}
    for page in pages:
        site = page.get("site", "unknown")
        if site not in sites:
            sites[site] = {
                "total": 0,
                "missing_seo_title": 0,
                "missing_description": 0,
                "missing_tags": 0,
            }
        s = sites[site]
        s["total"] += 1
        if not page.get("seo_title"):
            s["missing_seo_title"] += 1
        if not page.get("description"):
            s["missing_description"] += 1
        if not page.get("tags"):
            s["missing_tags"] += 1

    doc = {
        "generated_by": "analyze.py",
        "run_at": date.today().isoformat(),
        "total_pages": total,
        "pages_missing_seo_title": missing_seo_title,
        "pages_missing_description": missing_description,
        "pages_missing_tags": missing_tags,
        "pct_missing_seo_title": round(missing_seo_title / total * 100, 1) if total else 0,
        "pct_missing_description": round(missing_description / total * 100, 1) if total else 0,
        "pct_missing_tags": round(missing_tags / total * 100, 1) if total else 0,
        "by_site": sites,
    }

    GAP_SUMMARY_PATH.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"seo_gap_summary.json written to: {GAP_SUMMARY_PATH}")


# ---------------------------------------------------------------------------
# CLI — print summary table
# ---------------------------------------------------------------------------


def _print_summary_table(result: dict) -> None:
    print()
    print("=" * 60)
    print("  SEO OPPORTUNITY ANALYSIS — SUMMARY")
    print("=" * 60)
    print(f"  Run date             : {result['run_at']}")
    print(f"  Total pages analyzed : {result['total_pages_analyzed']}")
    print(f"    via Schema B (url)  : {result.get('schema_b_matches', 0)}")
    print(f"    via Schema A (title): {result.get('schema_a_matches', 0)}")
    print()
    print("  Opportunity breakdown:")
    summary = result.get("summary", {})
    for level in ("HIGH", "MEDIUM", "LOW", "SKIP"):
        count = summary.get(level, 0)
        bar = "#" * min(count, 40)
        print(f"    {level:<7} {count:>5}  {bar}")
    print()

    # Print 2 actionable examples (non-SKIP)
    opps = result.get("opportunities", [])
    actionable = [o for o in opps if o.get("opportunity_level") != "SKIP"]
    if actionable:
        print("  Example opportunities (non-SKIP, up to 2):")
        print()
        for opp in actionable[:2]:
            print(f"  Path     : {opp['page_path']}")
            print(f"  Level    : {opp['opportunity_level']}")
            print(f"  Reason   : {opp['score_reason']}")
            sig = opp.get("signals", {})
            print(f"  Zone     : {sig.get('position_zone', 'n/a')}")
            print(f"  CTR gap  : {sig.get('ctr_gap', False)}")
            print(f"  Title OK : {sig.get('title_aligned', False)}")
            print(f"  Desc OK  : {sig.get('description_ok', False)}")
            print(f"  Tag gaps : {sig.get('tag_gap_count', 0)}")
            kws = sig.get("matched_keywords", [])
            print(f"  Keywords : {kws[:5]}")
            print()
    else:
        print("  (No actionable opportunities found — all pages scored SKIP)")
        print()

    print(f"  opportunities.json   : {OPPORTUNITIES_PATH}")
    print(f"  seo_gap_summary.json : {GAP_SUMMARY_PATH}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== SEO-004 analyze.py — Opportunity Scorer ===")
    result = run_analysis()
    _print_summary_table(result)


if __name__ == "__main__":
    main()
