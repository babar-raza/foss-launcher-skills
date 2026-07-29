"""
SEO-KEYWORDS-FRONTMATTER-GROUNDING frontmatter_grounding.py
==============================================================
The mission's actual merge point for the two source plans' independent
keyword designs: a single three-tier priority for grounding a page's
`keywords:` frontmatter in something REAL, never fabricated.

Priority (highest first):
  1. gsc       -- real, English-matched Schema B (GSC) top queries for this
                  exact page's URL (scripts/seo/pipeline/keyword_lookup.py).
                  Strongest possible signal: actual searcher behavior.
  2. schema_a  -- a family-scoped, title-matched Schema A entry (LLM-
                  suggested keywords). Weaker than real GSC data, but still
                  grounded in a real, if lower-confidence, source.
  3. derived   -- extracted from the page's own ALREADY-VERIFIED
                  `description` frontmatter (never invents new claims;
                  only pulls significant terms out of text a human/agent
                  already wrote and grounded).
  none         -- no real signal available at any tier. Returning [] here
                  is the honest answer -- this module never pads with
                  generic filler just to satisfy page_role.py's >=5-keyword
                  count check. That check "becomes a real check instead of
                  theater once the source is truthful either way" (mission
                  design summary) -- this module is what makes it truthful;
                  it does not change the check itself.

This module is read-side only: it computes what tier/keywords WOULD apply
for a page, it does not write to any content file. See
frontmatter_grounding_audit.py for the read-only report over real content,
and the mission's plan (SEO-TITLE-PILOT-BACKFILL-PDF-DEVGUIDE precedent) for
why an actual content-frontmatter write is deliberately not attempted in
this same pass -- that requires the same governed, S-116-reviewed path
every other content write in this mission goes through.

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
KEYWORDS_DIR = _REPO_ROOT / "keywords"

try:
    from seo.pipeline.schema import classify_keyword_path, SCHEMA_A
    from seo.pipeline.keyword_lookup import top_queries_for_url
except ImportError:
    from schema import classify_keyword_path, SCHEMA_A
    from keyword_lookup import top_queries_for_url

SOURCE_GSC = "gsc"
SOURCE_SCHEMA_A = "schema_a"
SOURCE_DERIVED = "derived"
SOURCE_NONE = "none"

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "for", "to", "in", "on", "with",
    "is", "are", "as", "by", "at", "from", "this", "that", "it", "its", "your",
    "you", "using", "use", "without", "into", "via", "no", "any", "be", "can",
    "not", "when", "while", "including", "such", "these", "those", "their",
}


def _schema_a_lookup(family: str, page_title: str) -> list[str] | None:
    """Family-scoped, exact-title Schema A lookup. Returns None if the
    family has no Schema A file, it's not classified as Schema A (e.g.
    quarantined to empty -- an empty file classifies SCHEMA_UNKNOWN), or no
    entry matches this exact title.
    """
    path = KEYWORDS_DIR / f"{family}.json"
    if not path.exists() or classify_keyword_path(path) != SCHEMA_A:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in data:
        if isinstance(entry, dict) and entry.get("pageTitle") == page_title:
            kws = entry.get("keywords")
            if isinstance(kws, list) and kws:
                return kws
    return None


def _derive_from_description(description: str, limit: int = 5) -> list[str]:
    """Extract significant terms from an already-verified description --
    the lowest-priority tier. Never invents content beyond what's already
    written; just surfaces the most distinctive words already there.
    """
    if not description:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#_-]{2,}", description)
    seen: dict[str, int] = {}
    order: list[str] = []
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS:
            continue
        if lw not in seen:
            order.append(lw)
            seen[lw] = 0
        seen[lw] += 1
    # Prefer terms that recur, then fall back to first-seen order.
    ranked = sorted(order, key=lambda w: -seen[w])
    return ranked[:limit]


def ground_keywords_for_page(
    *,
    family: str,
    page_title: str,
    description: str | None = None,
    gsc_url: str | None = None,
) -> dict:
    """Return {"keywords": [...], "keyword_source": "gsc"|"schema_a"|"derived"|"none"}.

    Never raises. Never returns a non-empty keyword list without a truthful
    keyword_source marker identifying exactly where it came from.
    """
    if gsc_url:
        try:
            queries = top_queries_for_url(gsc_url)
        except Exception:
            queries = None
        if queries:
            return {
                "keywords": [q.get("query") for q in queries if q.get("query")],
                "keyword_source": SOURCE_GSC,
            }

    schema_a_kws = _schema_a_lookup(family, page_title) if page_title else None
    if schema_a_kws:
        return {"keywords": schema_a_kws, "keyword_source": SOURCE_SCHEMA_A}

    derived = _derive_from_description(description) if description else []
    if derived:
        return {"keywords": derived, "keyword_source": SOURCE_DERIVED}

    return {"keywords": [], "keyword_source": SOURCE_NONE}
