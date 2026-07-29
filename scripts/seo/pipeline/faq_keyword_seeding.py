"""
SEO-FAQ-KEYWORD-SEEDING faq_keyword_seeding.py
=================================================
Suggest candidate FAQ question TOPICS grounded in real keyword demand
(Schema B GSC queries, family-level aggregate -- an individual FAQ page's
GSC history doesn't exist until the page itself does, so per-URL matching
like frontmatter_grounding.py's gsc tier isn't available at generation
time). Consumed by S-22 (faq-generate)/S-59 (new-kb-faq) as an ADDITIONAL
input alongside their existing claims.json-grounded question extraction.

Anti-fabrication guard (the mission's own hard rule, restated here because
this is exactly where it is easiest to violate by accident): a suggested
topic is evidence of real search DEMAND, never evidence that a claim about
it is TRUE. Every suggestion returned here is explicitly marked
unverified_against_claims=True and carries no answer text at all -- only a
topic string and its real query/impression evidence. The skill consuming
this module is responsible for checking the topic against
claims.json/formats.json/limitations.md before turning it into an actual
FAQ question; this module cannot and does not perform that check itself
(it has no access to the family's knowledge model), so it never claims a
suggestion is already grounded.

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

try:
    from seo.pipeline.keyword_lookup import top_queries_for_family_site
except ImportError:
    from keyword_lookup import top_queries_for_family_site

# Sites where a KB FAQ page's own family might show real aggregate demand.
_FAQ_RELEVANT_SITES = ("kb.aspose.org", "docs.aspose.org")


def suggest_faq_question_topics(family: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` real-demand FAQ topic candidates for `family`.

    Each entry: {"topic_hint": <real query text>, "impressions": <int>,
    "source_site": <site>, "unverified_against_claims": True}.

    Returns [] if no real query data exists for this family at all -- the
    common case (Finding #3: GSC signal is thin). An empty list here means
    "no keyword-demand signal to seed with", never "no valid FAQ topics" --
    S-22/S-59's existing claims-only extraction path is unaffected either
    way and remains the primary generation mechanism.
    """
    collected: list[dict] = []
    for site in _FAQ_RELEVANT_SITES:
        try:
            queries = top_queries_for_family_site(site, family, limit=limit)
        except Exception:
            queries = None
        if not queries:
            continue
        for q in queries:
            query_text = q.get("query")
            if not query_text:
                continue
            collected.append({
                "topic_hint": query_text,
                "impressions": q.get("impressions", 0),
                "source_site": site,
                "unverified_against_claims": True,
            })

    collected.sort(key=lambda e: -e["impressions"])
    # Dedup by topic_hint, keeping the highest-impression occurrence.
    seen: set[str] = set()
    deduped: list[dict] = []
    for entry in collected:
        if entry["topic_hint"] in seen:
            continue
        seen.add(entry["topic_hint"])
        deduped.append(entry)

    return deduped[:limit]
