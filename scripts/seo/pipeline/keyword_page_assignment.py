"""
SEO-KEYWORD-PAGE-ASSIGNMENT keyword_page_assignment.py
========================================================
Contract B (v14 design authority: C:\\Users\\prora\\.claude\\plans\\
check-keywords-this-data-curious-feather.md, lines 628-659) — keyword-to-page
assignment + cannibalization gate.

No `query -> [urls]` structure exists anywhere in this repo's collected data:
Schema B (`keywords/{site}.json`) is strictly URL-keyed, each `queries[]`
entry carrying only its own URL's metrics. This module builds that missing
index by grouping every URL block's queries by query string, across every
Schema B file (cross-site union, not per-site) -- required for the first
release, not a deferred nicety, per Finding #82: a per-site-only index
produces a false "NONE" verdict that reads as verified-safe when only one of
several sites carrying real traffic for the same query was actually checked.

Real, currently-live cross-site cannibalization case (re-verified 2026-09-05,
see TestRealCrossSiteCase): the query "net pdf annotation" independently
ranks kb.aspose.org/pdf/net/how-to-add-pdf-annotations-dotnet/ AND
blog.aspose.org/pdf/net/pdf-annotations-forms-net/ -- two different site
files, both well above the impression floor, discoverable only by a
cross-site union index.

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from seo.pipeline.schema import classify_keyword_file, SCHEMA_B
except ImportError:
    from schema import classify_keyword_file, SCHEMA_B

REPO_ROOT = Path(__file__).resolve().parents[3]
KEYWORDS_DIR = REPO_ROOT / "keywords"

# Verdict values (plain string constants, matching this codebase's existing
# schema.py convention -- not enum.Enum, so every result is a JSON-plain dict
# with no custom serialization needed).
CANNIBALIZATION_NONE = "none"
CANNIBALIZATION_RISK = "risk"
CANNIBALIZATION_AMBIGUOUS = "ambiguous"

PLACEMENT_DO_NOT_USE = "do_not_use"
PLACEMENT_HUMAN_REVIEW = "human_review"

# Same "meaningful signal" floor analyze.py already uses (_IMPRESSION_THRESHOLD).
DEFAULT_IMPRESSION_FLOOR = 10
DEFAULT_POSITION_MARGIN = 3.0

# Approved locale-code set (this repo's translation project's 25 codes, plus
# a few legacy/pre-migration codes still present in older URLs) -- used only
# to recognize "the same page, a different locale" URL pairs, e.g.
# products.aspose.org/pt/pdf/ vs products.aspose.org/ru/pdf/, so the
# cannibalization gate does not flood editors with false HUMAN_REVIEW noise
# on legitimate locale variants of one page (Finding #82's locale-pair fix).
_LOCALE_CODES = {
    "ar", "cs", "de", "el", "es", "fa", "fr", "he", "hi", "hu", "id", "it",
    "ja", "ko", "nl", "pl", "pt", "ro", "ru", "sv", "th", "tr", "uk", "vi",
    "zh", "en", "ca", "da", "fi", "lt", "lv", "ms", "no", "sk", "sr", "bg",
}


# ---------------------------------------------------------------------------
# Loading Schema B entries (cross-site union or single-site)
# ---------------------------------------------------------------------------


def _iter_schema_b_records(keywords_dir: Path):
    """Yield (site, record) for every Schema B entry across every keywords/
    *.json file. Structural classification (schema.py), never a filename
    allowlist -- see map_url.py's own docstring for why that matters here."""
    for path in sorted(keywords_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.warn(f"keyword_page_assignment.py: could not parse {path.name}: {exc}")
            continue
        if classify_keyword_file(raw) != SCHEMA_B:
            continue
        if not isinstance(raw, list):
            continue
        site = path.stem  # e.g. "docs.aspose.org"
        for entry in raw:
            if isinstance(entry, dict):
                yield site, entry


# ---------------------------------------------------------------------------
# Query index
# ---------------------------------------------------------------------------


def build_query_index(
    site: "str | None" = None,
    keywords_dir: "Path | None" = None,
    union_all_sites: bool = True,
) -> dict[str, list[dict]]:
    """Pure, deterministic. Groups keywords/*.json queries[] by query string.

    union_all_sites=True (default): iterates every Schema B file, tagging
    each ranking with its site -- required for correct cross-site
    cannibalization detection (Finding #82).
    union_all_sites=False: restricts to exactly `site`'s own file (a
    same_site_only index, useful only for diagnostics -- never pass the
    result of this mode to check_cannibalization without also disclosing
    same_site_only=True in any surfaced result, per the design doc's own
    labeling requirement).

    Returns {query: [ranking, ...]}, each ranking a plain dict
    {query, url, site, impressions, position}. Each list is sorted
    (impressions desc, url asc) for byte-identical `json.dumps(...,
    sort_keys=True)` output on every run against the same input files.
    """
    if keywords_dir is None:
        keywords_dir = KEYWORDS_DIR
    if not union_all_sites and not site:
        raise ValueError("site is required when union_all_sites=False")

    index: dict[str, list[dict]] = {}
    for rec_site, rec in _iter_schema_b_records(keywords_dir):
        if not union_all_sites and rec_site != site:
            continue
        url = rec.get("url", "")
        for q in rec.get("queries") or []:
            query = q.get("query")
            if not query or not url:
                continue
            index.setdefault(query, []).append({
                "query": query,
                "url": url,
                "site": rec_site,
                "impressions": q.get("impressions", 0),
                "position": q.get("position", 0.0),
            })

    for rankings in index.values():
        rankings.sort(key=lambda r: (-r["impressions"], r["url"]))

    return index


# ---------------------------------------------------------------------------
# Locale-pair exclusion
# ---------------------------------------------------------------------------


def _strip_leading_locale_segment(path_str: str) -> str:
    parts = [p for p in path_str.split("/") if p]
    if parts and parts[0].lower() in _LOCALE_CODES:
        parts = parts[1:]
    return "/".join(parts)


def is_locale_pair(url_a: str, url_b: str) -> bool:
    """True iff url_a and url_b are the same page under two different
    locale-prefixed paths on the same domain (e.g. /pt/pdf/ vs /ru/pdf/) --
    legitimate locale variants, not competing content."""
    if url_a == url_b:
        return False
    pa, pb = urlparse(url_a), urlparse(url_b)
    if pa.netloc != pb.netloc:
        return False
    stripped_a = _strip_leading_locale_segment(pa.path)
    stripped_b = _strip_leading_locale_segment(pb.path)
    if stripped_a != stripped_b:
        return False
    # Only a genuine pair if at least one side actually had a locale prefix
    # (two identical paths with no locale segment at all are the same URL,
    # already excluded above; guards against an accidental empty-vs-empty match).
    return pa.path != pb.path


# ---------------------------------------------------------------------------
# Cannibalization check
# ---------------------------------------------------------------------------


def check_cannibalization(
    query: str,
    candidate_url: str,
    index: dict[str, list[dict]],
    *,
    position_margin: float = DEFAULT_POSITION_MARGIN,
    impression_floor: int = DEFAULT_IMPRESSION_FLOOR,
    claimed_this_run: "dict[str, str] | None" = None,
) -> dict:
    """Is `candidate_url` the right page to receive `query`, or does another
    page (possibly on another site) already own it?

    Returns a plain dict: {verdict, query, candidate_url, candidate_position,
    competitor_url, competitor_position, margin, placement_override,
    same_site_only, reasons}.

    Rules (Contract B, hardened per Findings #82/#83):
      - No floor-clearing, non-locale-pair competitor -> NONE (or AMBIGUOUS
        if the candidate itself doesn't clear the floor either -- genuinely
        low signal, not cannibalization; lowers confidence, does not block).
      - A competitor clears the floor but the candidate has no ranking at
        all for this query -> RISK / HUMAN_REVIEW (can't compute a margin,
        but the competitor already owns this keyword).
      - A competitor clears the floor and beats the candidate by
        >= position_margin -> RISK / DO_NOT_USE, softened to HUMAN_REVIEW
        when impressions differ by more than 2x (positions "close" relative
        to a noisy, low-volume signal).
      - A competitor leads by less than position_margin -> NONE. Documented,
        known residual gap (v1 scope, not fully closed): a real near-miss
        exists live on reference.aspose.org's "saveformat" query (margin
        ~1-2, ratio ~1.1x, both clearing the floor) that this rule set does
        not catch -- see TestKnownResidualNearMissGap.
      - Cross-site union: floor-clearing data for this query in more than
        one site (excluding locale pairs of the candidate) forces RISK /
        HUMAN_REVIEW regardless of the same-site verdict above.
      - In-run claimed-queries: if `claimed_this_run` already maps this
        query to a *different* URL (an earlier page in the same batch), this
        call forces HUMAN_REVIEW too -- the index is a frozen read of
        historical data and cannot see a same-run collision on its own.
    """
    rankings = index.get(query, [])

    candidate_ranking = next((r for r in rankings if r["url"] == candidate_url), None) if rankings else None
    candidate_has_data = candidate_ranking is not None
    candidate_position = candidate_ranking["position"] if candidate_ranking else None
    candidate_impressions = candidate_ranking["impressions"] if candidate_ranking else 0
    candidate_clears_floor = candidate_has_data and candidate_impressions >= impression_floor

    non_locale_pair = [
        r for r in rankings
        if r["url"] != candidate_url and not is_locale_pair(r["url"], candidate_url)
    ]
    floor_clearing_competitors = [r for r in non_locale_pair if r["impressions"] >= impression_floor]

    floor_clearing_all_non_locale_pair = [
        r for r in rankings
        if r["impressions"] >= impression_floor
        and (r["url"] == candidate_url or not is_locale_pair(r["url"], candidate_url))
    ]
    distinct_sites = {r["site"] for r in floor_clearing_all_non_locale_pair}
    cross_site = len(distinct_sites) > 1

    verdict = CANNIBALIZATION_NONE
    placement_override: "str | None" = None
    competitor_url: "str | None" = None
    competitor_position: "float | None" = None
    margin: "float | None" = None
    reasons: list[str] = []

    if not floor_clearing_competitors:
        if not rankings:
            reasons.append("no data at all for this query")
        elif candidate_clears_floor:
            reasons.append("no floor-clearing non-locale-pair competitor found")
        else:
            # Either the candidate has some sub-floor data of its own, or it
            # has none at all but other sub-floor/locale-pair noise exists
            # for this query -- both are "genuinely low signal", not a
            # confident NONE.
            verdict = CANNIBALIZATION_AMBIGUOUS
            reasons.append(
                f"neither the candidate nor any non-locale-pair competitor clears "
                f"the {impression_floor}-impression floor for {query!r}"
            )
    else:
        best_competitor = min(floor_clearing_competitors, key=lambda r: r["position"])
        competitor_url = best_competitor["url"]
        competitor_position = best_competitor["position"]

        if not candidate_has_data:
            verdict = CANNIBALIZATION_RISK
            placement_override = PLACEMENT_HUMAN_REVIEW
            reasons.append(
                f"{competitor_url!r} already clears the impression floor for "
                f"{query!r} but the candidate page has no ranking data at all"
            )
        else:
            margin = candidate_position - competitor_position
            if margin >= position_margin:
                verdict = CANNIBALIZATION_RISK
                lo = max(1, min(candidate_impressions, best_competitor["impressions"]))
                hi = max(candidate_impressions, best_competitor["impressions"])
                imp_ratio = hi / lo
                if imp_ratio > 2.0:
                    placement_override = PLACEMENT_HUMAN_REVIEW
                    reasons.append(
                        f"{competitor_url!r} beats candidate by {margin:.2f} positions but "
                        f"impressions differ {imp_ratio:.1f}x -- softened to human review"
                    )
                else:
                    placement_override = PLACEMENT_DO_NOT_USE
                    reasons.append(
                        f"{competitor_url!r} beats candidate by {margin:.2f} positions "
                        f"(>= {position_margin} margin) for {query!r}"
                    )
            elif margin > 0:
                reasons.append(
                    f"known residual gap (v1 scope, Finding #82): {competitor_url!r} leads "
                    f"by only {margin:.2f} positions (< {position_margin} margin) -- not flagged"
                )
            else:
                reasons.append("candidate is best-positioned among floor-clearing URLs")

    if cross_site:
        verdict = CANNIBALIZATION_RISK
        placement_override = PLACEMENT_HUMAN_REVIEW
        reasons.append(
            f"cross-site union: {query!r} has floor-clearing data in "
            f"{sorted(distinct_sites)} -- forcing human review regardless of "
            "the same-site verdict"
        )

    if claimed_this_run is not None:
        prior_url = claimed_this_run.get(query)
        if prior_url is not None and prior_url != candidate_url:
            placement_override = PLACEMENT_HUMAN_REVIEW
            reasons.append(
                f"{query!r} already claimed by {prior_url!r} earlier in this run"
            )

    return {
        "verdict": verdict,
        "query": query,
        "candidate_url": candidate_url,
        "candidate_position": candidate_position,
        "competitor_url": competitor_url,
        "competitor_position": competitor_position,
        "margin": margin,
        "placement_override": placement_override,
        "same_site_only": not cross_site,
        "reasons": reasons,
    }
