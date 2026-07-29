"""
SEO-SITE-PLANNER-DEMAND-TIEBREAK-SCHEMA-B demand_hints.py
============================================================
Compute {class_name: demand_score} from real Schema B (GSC) query data, for
use as site_planner.py's detect_clusters() optional demand_hints tie-breaker.

Design constraint (mission decision, Context section): search-demand signal
may prove DEMAND, never TRUTH -- this module only ever attributes a real,
already-observed GSC query's impressions to a real, already-known API class
name (from api_surface.json). It never invents a class, a claim, or a
cluster. A class with zero matching query text gets a demand_score of 0.0,
which is the correct "no evidence either way" default (site_planner.py's own
tie-break rule then falls through to claim_count-based ordering unaffected).

Schema B lane only (Schema A is explicitly DEFERRED_WITH_REASON per the
mission plan -- stub-tier families have no knowledge/ artifacts yet, so
there is nothing claims-eligible to tie-break against).

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Sites that organize content by family (site_domain, needs a /{family}/
# path segment) -- the same universe keyword_lookup.top_queries_for_family_site
# already expects.
_FAMILY_SITES = ("docs.aspose.org", "kb.aspose.org", "blog.aspose.org")

_CLASS_NAME_MIN_LEN = 4  # avoid short class names (e.g. "Row") matching noise


def _class_name_variants(class_name: str) -> list[str]:
    """Lowercase forms of a class name worth searching for in query text:
    the name itself, and its snake_case split (e.g. "PdfDocument" ->
    "pdf document") since real queries are natural-language phrases, not
    CamelCase identifiers.
    """
    variants = {class_name.lower()}
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name).lower()
    if spaced != class_name.lower():
        variants.add(spaced)
    return list(variants)


def compute_demand_hints(family: str, api_surface: list[dict]) -> dict[str, float]:
    """Return {class_name: total_matched_impressions} for `family`.

    Only real class names present in api_surface are ever keys -- this
    function cannot introduce a class that doesn't already exist in the
    knowledge model. Returns {} if no query data is available for this
    family at all (the common case for most families -- Finding #3: real
    GSC signal covers a small fraction of launched families).
    """
    try:
        from seo.pipeline.keyword_lookup import top_queries_for_family_site
    except Exception:
        return {}

    class_names = sorted({
        entry.get("name", "")
        for entry in api_surface
        if isinstance(entry, dict) and len(entry.get("name", "")) >= _CLASS_NAME_MIN_LEN
    })
    if not class_names:
        return {}

    all_queries: list[dict] = []
    for site in _FAMILY_SITES:
        try:
            queries = top_queries_for_family_site(site, family, limit=50)
        except Exception:
            queries = None
        if queries:
            all_queries.extend(queries)
    if not all_queries:
        return {}

    query_texts = [
        (q.get("query", "") or "").lower()
        for q in all_queries
        if isinstance(q, dict)
    ]

    hints: dict[str, float] = {}
    for cls_name in class_names:
        variants = _class_name_variants(cls_name)
        matched_impressions = 0.0
        for q, text in zip(all_queries, query_texts):
            if any(v in text for v in variants):
                matched_impressions += q.get("impressions", 0)
        if matched_impressions > 0:
            hints[cls_name] = matched_impressions

    return hints
