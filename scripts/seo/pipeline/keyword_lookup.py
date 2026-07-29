"""
SEO-000b keyword_lookup.py
===========================
Shared URL -> top-queries lookup over the real Schema B (GSC) keyword files.

Every later-phase consumer in the seo-keyword-production-integration mission
(title templates, FAQ keyword seeding, traffic-tier prioritization,
content-gap detection) is meant to read through this module instead of
re-parsing keywords/*.json independently -- exactly the kind of duplication
that let validate.py and map_url.py's Schema A/B classification silently
drift apart before schema.py existed (Findings #1/#36 in the mission plan).

Scope, deliberately narrow (Finding #3): English-URL-matched only. Real GSC
signal covers ~150-190 English URLs total across all 7 sites -- the large
majority of pages have no row here at all. This module never fabricates
signal for an unmatched URL; callers get an explicit "no data" result
(`None` from top_queries_for_url), never a zero standing in for "unknown".

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from seo.pipeline.schema import classify_keyword_file, SCHEMA_B
except ImportError:
    from schema import classify_keyword_file, SCHEMA_B

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[3]
KEYWORDS_DIR = _REPO_ROOT / "keywords"


def _load_schema_b_entries(keywords_dir: Path | None = None) -> list[dict]:
    """Return every raw Schema B entry across all real GSC keyword files.

    Structural classification (schema.py), not a filename list -- so this
    stays correct even if the set of Schema B files changes.
    """
    if keywords_dir is None:
        keywords_dir = KEYWORDS_DIR
    entries: list[dict] = []
    for path in sorted(keywords_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if classify_keyword_file(raw) != SCHEMA_B:
            continue
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and "url" in entry:
                    entry = dict(entry)
                    entry["_source_file"] = path.name
                    entries.append(entry)
    return entries


def load_all_queries(keywords_dir: Path | None = None) -> dict[str, dict]:
    """Return {url: entry} for every English-language Schema B URL entry.

    Non-English entries are excluded entirely (Finding #3: real per-locale
    GSC signal for non-English URLs is near-zero and frequently just a
    site-search-operator artifact, not a real query -- confirmed by direct
    inspection of the raw keyword data during this mission).
    """
    entries = _load_schema_b_entries(keywords_dir)
    result: dict[str, dict] = {}
    for entry in entries:
        if entry.get("lang") != "en":
            continue
        url = entry.get("url")
        if not url:
            continue
        result[url] = entry
    return result


def top_queries_for_url(
    url: str,
    limit: int = 5,
    keywords_dir: Path | None = None,
) -> list[dict] | None:
    """Return up to `limit` queries for `url`, sorted by impressions desc.

    Returns None (explicit no-data) if the URL has no English Schema B
    entry -- the common case for the vast majority of pages. Callers MUST
    treat None as "no real signal", never as "zero demand" or a stand-in
    for a derived/fallback value.
    """
    all_queries = load_all_queries(keywords_dir)
    entry = all_queries.get(url)
    if entry is None:
        return None
    queries = entry.get("queries") or []
    if not queries:
        return None
    ranked = sorted(queries, key=lambda q: q.get("impressions", 0), reverse=True)
    return ranked[:limit]


def top_queries_for_family_site(
    site_domain: str,
    family: str,
    limit: int = 5,
    keywords_dir: Path | None = None,
) -> list[dict] | None:
    """Return up to `limit` queries across all English URLs for a given
    site+family (e.g. site_domain="docs.aspose.org", family="pdf"),
    aggregated and sorted by impressions desc.

    Useful when no single-page match exists but a family-level signal
    might still ground a title clause or FAQ question -- callers must
    still treat this as a weaker prior than a direct per-URL match
    (Finding #22's title-formula design explicitly downgrades family-level
    signal to "word-choice hint only", never clause content by itself).

    Returns None if no matching URLs have any query data.
    """
    all_queries = load_all_queries(keywords_dir)
    needle = f"//{site_domain}/{family}"
    collected: list[dict] = []
    for url, entry in all_queries.items():
        if needle not in url and f"//{site_domain}" not in url:
            continue
        if f"/{family}/" not in url and not url.rstrip("/").endswith(f"/{family}"):
            continue
        collected.extend(entry.get("queries") or [])
    if not collected:
        return None
    ranked = sorted(collected, key=lambda q: q.get("impressions", 0), reverse=True)
    return ranked[:limit]
