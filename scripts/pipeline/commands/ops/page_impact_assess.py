#!/usr/bin/env python3
"""page_impact_assess.py — Page Impact Assessment (PIA) for post-refresh content review.

CONTRACT: scripts/pipeline/commands/ops/page_impact_assess.py
  purpose: Score every English content page against the knowledge delta to identify
           which pages need body review after an upstream knowledge refresh.
  inputs:  knowledge/{family}/{platform}/merged/knowledge_delta.json
           content pages (all 5 subdomains) for the given family/platform
  outputs: reports/refresh_review/{family}/{platform}/page_impact.json
  idempotent: yes — overwrites output on each run

Impact score legend:
  HIGH_IMPACT           — page body contains a class or method name matching modified_apis, removed_apis, or new_apis
  MEDIUM_IMPACT         — page body contains a keyword matching modified_claims, removed_claims, or new_claims topics
  LOW_IMPACT            — no strong delta signals found; page may still benefit from review
  NOT_AFFECTED          — no delta signals detected; page topic unrelated to knowledge changes
  ENRICHMENT_CANDIDATE  — page covers a feature cluster that has new_apis but does not yet
                          reference those new API member names (add-only coverage gap)

Usage:
    .venv/Scripts/python scripts/pipeline/commands/ops/page_impact_assess.py {family} {platform}
    .venv/Scripts/python scripts/pipeline/commands/ops/page_impact_assess.py cells net --knowledge-root knowledge/
    .venv/Scripts/python scripts/pipeline/commands/ops/page_impact_assess.py cells net --json

Exit codes:
    0  — assessment complete (even if all pages NOT_AFFECTED)
    1  — fatal error (knowledge_delta.json missing and --require-delta set, or I/O failure)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from content_discovery import LOCALE_RE, _is_draft  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _url_map_cache
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _url_map_cache = None

# Site pattern tuples: (subdomain_label, path_pattern_relative_to_content_root)
# Must match stale_detect.py _SITE_PATTERNS for consistency.
_SITE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("docs",      "docs.aspose.org/en/{family}/{platform}"),
    ("kb",        "kb.aspose.org/en/{family}/{platform}"),
    ("products",  "products.aspose.org/en/{family}/{platform}"),
    ("reference", "reference.aspose.org/en/{family}/{platform}"),
    ("blog",      "blog.aspose.org/{family}/{platform}"),
)


def _discover_pages(
    content_root: Path,
    family: str,
    platform: str,
) -> list[tuple[Path, str]]:
    """Return (path, subdomain) pairs for all English non-draft .md files."""
    results: list[tuple[Path, str]] = []
    for subdomain, pattern in _SITE_PATTERNS:
        site_root = content_root / pattern.format(family=family, platform=platform)
        if not site_root.exists():
            continue
        for path in sorted(site_root.rglob("*.md")):
            if LOCALE_RE.search(path.name):
                continue
            if _is_draft(path):
                continue
            results.append((path, subdomain))
    return results


# ---------------------------------------------------------------------------
# SEO-PIA-TRAFFIC-TIER-FIELD: order-only, non-authoritative traffic signal.
#
# traffic_tier NEVER affects pia_score or which pages are in scope for a
# refresh run (_paths_from_pia() in refresh_run.py filters on pia_score
# alone, unchanged by this addition) -- it exists purely so a downstream
# consumer (body_refresh.py's per-page processing loop) can choose to
# process higher-real-traffic pages first within an already-decided scope.
# Real GSC signal in this repo is thin (Finding #3: ~150-190 English URLs
# total) so a page with zero rows here is the overwhelmingly common case --
# "no-data" must never be read as "zero demand", only as "no measurement".
#
# Both scripts/seo/pipeline modules are imported lazily and defensively: PIA
# is core pipeline infrastructure used well beyond this SEO mission, so it
# must degrade to "no-data" cleanly (never raise) if the seo subpackage is
# ever unavailable, moved, or its optional data files are missing.
# ---------------------------------------------------------------------------

_TRAFFIC_TIER_NO_DATA = "no-data"
_TRAFFIC_TIER_HIGH = "high"
_TRAFFIC_TIER_MEDIUM = "medium"
_TRAFFIC_TIER_HIGH_MIN_IMPRESSIONS = 50

_url_map_cache: dict[str, str] | None = None


def _content_path_to_gsc_url_map() -> dict[str, str]:
    """Build (once, cached) {content_path: gsc_url} from map_url.py's real
    URL resolution -- the inverse of what map_url.py itself computes.
    Returns {} on any import/build failure (defensive -- see module note).
    """
    global _url_map_cache
    if _url_map_cache is not None:
        return _url_map_cache

    _url_map_cache = {}
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from seo.pipeline.map_url import build_url_map
        result = build_url_map()
        for entry in result.get("url_map", []):
            content_path = entry.get("content_path")
            gsc_url = entry.get("gsc_url")
            if content_path and gsc_url:
                _url_map_cache[content_path] = gsc_url
    except Exception:
        # Defensive: PIA must never fail because the SEO subsystem is
        # unavailable, mid-refactor, or missing optional data.
        _url_map_cache = {}
    return _url_map_cache


def traffic_tier_for_path(rel_path: str) -> str:
    """Return 'high' | 'medium' | 'no-data' for a repo-relative content path.

    'high': real GSC query data exists with >= _TRAFFIC_TIER_HIGH_MIN_IMPRESSIONS
            total impressions across its top queries.
    'medium': real GSC query data exists, below that threshold.
    'no-data': no GSC URL maps to this path, or no query rows for that URL --
               the default for the large majority of pages in this repo.
    """
    url = _content_path_to_gsc_url_map().get(rel_path)
    if not url:
        return _TRAFFIC_TIER_NO_DATA
    try:
        from seo.pipeline.keyword_lookup import top_queries_for_url
        queries = top_queries_for_url(url)
    except Exception:
        return _TRAFFIC_TIER_NO_DATA
    if not queries:
        return _TRAFFIC_TIER_NO_DATA
    total_impressions = sum(q.get("impressions", 0) for q in queries)
    return _TRAFFIC_TIER_HIGH if total_impressions >= _TRAFFIC_TIER_HIGH_MIN_IMPRESSIONS else _TRAFFIC_TIER_MEDIUM


def _load_delta(knowledge_root: Path, family: str, platform: str) -> dict:
    """Load knowledge_delta.json; return {} if absent."""
    delta_path = knowledge_root / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.is_file():
        return {}
    try:
        return json.loads(delta_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _extract_api_names(delta: dict) -> set[str]:
    """Extract class and method names from modified_apis, removed_apis, and new_apis."""
    names: set[str] = set()
    for key in ("modified_apis", "removed_apis", "new_apis"):
        for entry in delta.get(key, []):
            if isinstance(entry, str):
                names.add(entry.lower())
            elif isinstance(entry, dict):
                class_name = entry.get("name") or entry.get("class_name") or ""
                if class_name:
                    names.add(class_name.lower())
                # Also index method names
                for method in entry.get("methods", []):
                    if isinstance(method, str):
                        names.add(method.lower())
                    elif isinstance(method, dict):
                        m = method.get("name") or ""
                        if m:
                            names.add(m.lower())
    return names


def _extract_claim_keywords(delta: dict) -> set[str]:
    """Extract significant keywords from modified/removed/new claim text."""
    keywords: set[str] = set()
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "of", "in", "to",
        "for", "on", "with", "at", "by", "from", "up", "about", "into",
        "than", "then", "so", "if", "or", "and", "but", "not", "no",
        "it", "its", "this", "that", "these", "those", "all", "any",
        "class", "method", "property", "object", "value", "type",
        "returns", "return", "true", "false", "null", "none",
        "new", "get", "set", "add", "use", "used", "using",
    }
    for key in ("modified_claims", "removed_claims", "new_claims"):
        for entry in delta.get(key, []):
            if isinstance(entry, str):
                text = entry
            elif isinstance(entry, dict):
                text = entry.get("text") or entry.get("description") or entry.get("claim_text") or ""
            else:
                continue
            # Extract meaningful words (4+ chars, no numbers-only, not stopwords)
            for word in re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b", text):
                w = word.lower()
                if w not in stopwords:
                    keywords.add(w)
    return keywords


# ---------------------------------------------------------------------------
# RPR-D-01: citation-based scoring — read the page's OWN evidence frontmatter
# (evidence.claims / evidence.apis) and match those cited IDs against the exact
# changed-ID sets from the delta, instead of guessing via body-text token
# overlap. The token heuristic below is retained ONLY as a logged-warning
# fallback for pages that carry no evidence frontmatter — never as the primary
# path when evidence is present (plan §2.3: PIA "never reads the page's own
# evidence.claims/evidence.apis frontmatter").
# ---------------------------------------------------------------------------


def _extract_changed_api_ids(delta: dict) -> set[str]:
    """Exact (case-preserved) API names/IDs from every changed set in the delta.

    Unlike _extract_api_names (which lowercases for token matching), this keeps
    original case because evidence.apis and api_surface names are case-sensitive
    and citation matching is exact, not fuzzy.
    """
    ids: set[str] = set()
    for key in ("modified_apis", "removed_apis", "new_apis", "resurrected_apis"):
        for entry in delta.get(key, []):
            if isinstance(entry, str):
                ids.add(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("class_name") or ""
                if name:
                    ids.add(name)
    # MT074 B2: enum constants added/removed on an existing type are changes to that type's
    # public surface -- a page citing "Type.Member" (or "Type") is affected. Exact,
    # case-preserved identifiers only (no lowercase body-token matching: constant names
    # such as short format words would match unrelated prose).
    # Removed constants are skipped while the removal is unconfirmed (extractor changed/unknown,
    # delta["breaking_unconfirmed"]): that is informational, not evidence the member is gone.
    unconfirmed = delta.get("breaking_unconfirmed", {}) or {}
    for owner, sig in (delta.get("api_signature_changes", {}) or {}).items():
        if not isinstance(sig, dict):
            continue
        for key in ("enum_members_added", "enum_members_removed"):
            if (key == "enum_members_removed" and isinstance(unconfirmed.get(owner), dict)
                    and unconfirmed[owner].get("enum_members_removed")):
                continue
            for member in sig.get(key, []) or []:
                if owner and member:
                    ids.add(f"{owner}.{member}")
    return ids


def _extract_changed_claim_ids(delta: dict) -> set[str]:
    """Exact claim IDs from every changed claim set in the delta."""
    ids: set[str] = set()
    for key in ("modified_claims", "removed_claims", "new_claims"):
        for entry in delta.get(key, []):
            if isinstance(entry, str):
                ids.add(entry)
            elif isinstance(entry, dict):
                cid = entry.get("claim_id") or entry.get("id") or ""
                if cid:
                    ids.add(cid)
    return ids


def _read_page_evidence(path: Path) -> tuple[list[str], list[str]]:
    """Return (evidence.claims, evidence.apis) from a page's frontmatter.

    Returns ([], []) when the page has no frontmatter, no evidence block, or is
    unreadable/malformed — callers must treat ([], []) as "no evidence to score
    from", NOT as "nothing changed".
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    if not text.startswith("---"):
        return [], []
    end = text.find("\n---", 3)
    if end == -1:
        return [], []
    fm_text = text[3:end]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        return [], []
    if not isinstance(fm, dict):
        return [], []
    ev = fm.get("evidence") or {}
    if not isinstance(ev, dict):
        return [], []
    claims = [str(c) for c in (ev.get("claims") or []) if c]
    apis = [str(a) for a in (ev.get("apis") or []) if a]
    return claims, apis


def _match_cited_apis(cited_apis: list[str], changed_api_ids: set[str]) -> set[str]:
    """Return the subset of cited APIs affected by the delta.

    A cited API matches when it is exactly in the changed set, OR when its
    owning class (the token before the first '.') is in the changed set — a
    page citing `Document.Create` is affected when the class `Document` changed,
    even if the delta tracks changes at class granularity only.
    """
    hits: set[str] = set()
    for cited in cited_apis:
        if cited in changed_api_ids:
            hits.add(cited)
            continue
        owning_class = cited.split(".", 1)[0]
        if owning_class and owning_class in changed_api_ids:
            hits.add(cited)
    return hits


def _score_page(
    path: Path,
    api_names: set[str],
    claim_keywords: set[str],
    *,
    changed_api_ids: set[str] | None = None,
    changed_claim_ids: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Return (pia_score, signals_found) for a single page.

    Primary path (RPR-D-01) — when the page carries an evidence frontmatter block
    AND changed-ID sets are supplied:
      - HIGH_IMPACT   : a cited API (exact or its owning class) is in the delta's
                        changed API set.
      - MEDIUM_IMPACT : a cited claim ID is in the delta's changed claim set.
      - LOW_IMPACT    : evidence present, but nothing it cites changed. (RPR-D-02
                        upgrades this specific case to NOT_AFFECTED.)

    Fallback path — when the page has NO evidence frontmatter (or no changed-ID
    sets were supplied): the legacy body-text token heuristic runs, and its
    signals are prefixed `fallback-*` so it is visible in the output that this
    page could not be citation-scored.
    """
    changed_api_ids = changed_api_ids or set()
    changed_claim_ids = changed_claim_ids or set()

    cited_claims, cited_apis = _read_page_evidence(path)
    has_evidence = bool(cited_claims or cited_apis)
    citation_scoring_available = has_evidence and (changed_api_ids or changed_claim_ids)

    if citation_scoring_available:
        api_hits = _match_cited_apis(cited_apis, changed_api_ids)
        if api_hits:
            return "HIGH_IMPACT", [f"cite-api:{a}" for a in sorted(api_hits)[:5]]

        claim_hits = set(cited_claims) & changed_claim_ids
        if claim_hits:
            return "MEDIUM_IMPACT", [f"cite-claim:{c}" for c in sorted(claim_hits)[:5]]

        # RPR-D-02: evidence present, and nothing this page cites is in the delta's
        # changed sets. This is a genuine, per-page NOT_AFFECTED — assignable even
        # when the product's overall delta is non-empty and sibling pages score
        # HIGH/MEDIUM. Before RPR-D-01/D-02, NOT_AFFECTED could only ever be
        # assigned product-wide (whole delta empty), so a page with zero overlap
        # was forced to LOW_IMPACT. A page reaches here ONLY via the citation path,
        # which requires non-empty evidence — an evidence-less page can never
        # silently default to NOT_AFFECTED (it takes the fallback path instead).
        return "NOT_AFFECTED", ["cite-clean"]

    # ── Fallback: legacy body-text token heuristic (evidence-less pages only) ──
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "NOT_AFFECTED", []

    # Strip frontmatter to get body text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        body = text[end + 4:] if end != -1 else text
    else:
        body = text

    body_lower = body.lower()
    body_tokens = set(re.findall(r"\b[a-z][a-z0-9]{2,}\b", body_lower))

    # Emit a visible marker so an evidence-less page's fallback scoring is never
    # mistaken for a confident citation-based verdict. Only added when the caller
    # actually supplied changed-ID sets (i.e. a real assess_product run) — the
    # legacy 3-arg _score_page(page, api_names, claim_keywords) call path (used by
    # older unit tests and any external caller) keeps its original signal shape.
    fallback_note = "fallback-no-evidence" if (changed_api_ids or changed_claim_ids) else None

    high_matches = api_names.intersection(body_tokens)
    if high_matches:
        signals = [f"api:{m}" for m in sorted(high_matches)[:5]]
        if fallback_note:
            signals.insert(0, fallback_note)
        return "HIGH_IMPACT", signals

    kw_matches = claim_keywords.intersection(body_tokens)
    if kw_matches and len(kw_matches) >= 2:
        signals = [f"kw:{k}" for k in sorted(kw_matches)[:5]]
        if fallback_note:
            signals.insert(0, fallback_note)
        return "MEDIUM_IMPACT", signals

    return "LOW_IMPACT", [fallback_note] if fallback_note else []


# ---------------------------------------------------------------------------
# ENRICHMENT_CANDIDATE detection
# ---------------------------------------------------------------------------

# Cluster definitions: each entry maps a cluster name to the set of
# lowercase keywords that signal a page discusses that topic cluster.
# A minimum of _ENRICHMENT_MIN_KEYWORDS matches is required before the
# cluster check fires (avoids false positives on generic index pages).
_CLUSTER_KEYWORDS: dict[str, set[str]] = {
    "Charts": {
        "chart", "charts", "chartcollection", "charttype", "chartmodel",
        "embedded", "getcharts", "getcount", "getcharttype",
    },
    "Comments": {
        "comment", "comments", "commentcollection", "commentmodel",
        "note", "author", "getcomment", "addcomment", "getnote",
    },
    "Pictures": {
        "picture", "pictures", "picturecollection", "picturemodel",
        "image", "imagetype", "getpictures", "embedded",
        "getimagedata", "getcontenttype",
    },
    "Shapes": {
        "shape", "shapes", "shapecollection", "shapemodel",
        "autoshape", "autoshapetype", "drawing", "getshapes",
        "geometrytype", "getgeometrytype",
    },
    "Tables": {
        "listobject", "listobjectcollection", "listcolumn",
        "listcolumnmodel", "tablestyle", "tablestyletype",
        "totalscalculation", "table", "structured",
        "gettables", "displayname", "showtotals",
    },
}

_ENRICHMENT_MIN_KEYWORDS = 3  # minimum cluster keyword matches to fire


def _cluster_for_api(api_name: str) -> str | None:
    """Return the cluster name that owns api_name, or None if unrecognised."""
    a = api_name.lower()
    for cluster, keywords in _CLUSTER_KEYWORDS.items():
        if a in keywords:
            return cluster
    # Also check prefix matching for compound names
    for cluster, keywords in _CLUSTER_KEYWORDS.items():
        for kw in keywords:
            if a.startswith(kw) or kw.startswith(a):
                return cluster
    return None


def detect_enrichment_candidates(
    pages: list[tuple[Path, str]],
    knowledge_delta: dict,
    api_surface: list[dict] | None = None,
) -> list[dict]:
    """Detect ENRICHMENT_CANDIDATE pages.

    A page is an ENRICHMENT_CANDIDATE when:
    - Its body contains >= _ENRICHMENT_MIN_KEYWORDS keywords from a cluster's
      keyword set (the page discusses that cluster's topic)
    - The page body does NOT already mention the new API member names that
      were added in this delta's new_apis list for that cluster
    - There are new_apis in the delta that belong to the cluster

    Args:
        pages: list of (Path, subdomain) pairs (output of _discover_pages)
        knowledge_delta: parsed knowledge_delta.json dict
        api_surface: parsed api_surface.json list (unused; reserved for future
                     use to cross-check class membership)

    Returns:
        list of dicts, each with keys:
          page_path   — repo-relative path string
          cluster_name — name of the feature cluster
          missing_apis — list of new API names not yet present in the page body
          confidence   — float 0.0–1.0 (keyword match ratio vs threshold)
    """
    new_apis: list[str] = knowledge_delta.get("new_apis", [])
    if not new_apis:
        return []

    # Group new_apis by cluster
    cluster_new_apis: dict[str, list[str]] = {}
    for api_name in new_apis:
        cluster = _cluster_for_api(api_name)
        if cluster is not None:
            cluster_new_apis.setdefault(cluster, []).append(api_name)

    if not cluster_new_apis:
        return []

    candidates: list[dict] = []

    for path, subdomain in pages:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Strip frontmatter
        if text.startswith("---"):
            end = text.find("\n---", 3)
            body = text[end + 4:] if end != -1 else text
        else:
            body = text

        body_lower = body.lower()
        body_tokens = set(re.findall(r"\b[a-z][a-z0-9]{2,}\b", body_lower))

        try:
            rel_path = str(path.relative_to(path.parents[len(path.parts) - 1])).replace("\\", "/")
        except Exception:
            rel_path = str(path).replace("\\", "/")

        for cluster_name, new_api_list in cluster_new_apis.items():
            cluster_kws = _CLUSTER_KEYWORDS[cluster_name]

            # Count how many cluster keywords appear in the body
            kw_matches = cluster_kws.intersection(body_tokens)
            match_count = len(kw_matches)

            if match_count < _ENRICHMENT_MIN_KEYWORDS:
                continue  # page does not discuss this cluster

            # Check which new API names are missing from the page body
            missing_apis = [
                api for api in new_api_list
                if api.lower() not in body_tokens
            ]

            if not missing_apis:
                continue  # page already references all new APIs in this cluster

            # Confidence: ratio of keyword matches to the cluster keyword set size,
            # clamped to [0.0, 1.0].  Scaled by the fraction of missing APIs.
            kw_ratio = min(1.0, match_count / max(len(cluster_kws), 1))
            missing_ratio = len(missing_apis) / max(len(new_api_list), 1)
            confidence = round(kw_ratio * missing_ratio, 4)

            candidates.append({
                "page_path": str(path).replace("\\", "/"),
                "subdomain": subdomain,
                "cluster_name": cluster_name,
                "missing_apis": missing_apis,
                "keyword_matches": sorted(kw_matches),
                "confidence": confidence,
            })

    return candidates


def assess_product(
    family: str,
    platform: str,
    *,
    content_root: Path | None = None,
    knowledge_root: Path | None = None,
) -> dict:
    """Run PIA for all English content pages of a product.

    Returns a dict with structure::

        {
          "family": ..., "platform": ...,
          "delta_sha": ...,
          "api_signals_count": N,
          "claim_keyword_count": N,
          "pages": [
            {"path": ..., "subdomain": ..., "pia_score": ..., "signals_found": [...],
             "traffic_tier": "high"|"medium"|"no-data"},
            ...
          ],
          "summary": {
            "HIGH_IMPACT": N, "MEDIUM_IMPACT": N,
            "LOW_IMPACT": N, "NOT_AFFECTED": N,
            "total": N
          }
        }
    """
    if content_root is None:
        content_root = _REPO_ROOT / "content"
    if knowledge_root is None:
        knowledge_root = _REPO_ROOT / "knowledge"

    delta = _load_delta(knowledge_root, family, platform)
    delta_sha = delta.get("current_sha") or delta.get("base_sha") or ""

    api_names = _extract_api_names(delta)
    claim_keywords = _extract_claim_keywords(delta)
    # RPR-D-01: exact changed-ID sets for citation-based scoring (primary path).
    changed_api_ids = _extract_changed_api_ids(delta)
    changed_claim_ids = _extract_changed_claim_ids(delta)

    pages_data = []
    summary: dict[str, int] = {
        "HIGH_IMPACT": 0,
        "MEDIUM_IMPACT": 0,
        "LOW_IMPACT": 0,
        "NOT_AFFECTED": 0,
        "total": 0,
    }

    # Compute repo root for relative path calculation.
    # content_root is typically {repo_root}/content, so repo_root = content_root.parent.
    # For tests that pass a tmp_path, this still produces correct relative paths.
    effective_repo_root = content_root.parent

    page_pairs = _discover_pages(content_root, family, platform)
    for path, subdomain in page_pairs:
        try:
            rel_path = str(path.relative_to(effective_repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(path).replace("\\", "/")

        if not api_names and not claim_keywords:
            # No delta signals — all pages are NOT_AFFECTED (delta absent or empty)
            score, signals = "NOT_AFFECTED", []
        else:
            score, signals = _score_page(
                path, api_names, claim_keywords,
                changed_api_ids=changed_api_ids,
                changed_claim_ids=changed_claim_ids,
            )

        pages_data.append({
            "path": rel_path,
            "subdomain": subdomain,
            "pia_score": score,
            "signals_found": signals,
            # Order-only signal, never authoritative for scope -- see
            # traffic_tier_for_path()'s docstring and the module note above.
            "traffic_tier": traffic_tier_for_path(rel_path),
        })
        summary[score] = summary.get(score, 0) + 1
        summary["total"] += 1

    enrichment_candidates = detect_enrichment_candidates(page_pairs, delta)

    return {
        "family": family,
        "platform": platform,
        "delta_sha": delta_sha,
        "api_signals_count": len(api_names),
        "claim_keyword_count": len(claim_keywords),
        "pages": pages_data,
        "summary": summary,
        "enrichment_candidates": enrichment_candidates,
        "enrichment_candidates_count": len(enrichment_candidates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="page_impact_assess",
        description="Score content pages against knowledge delta for post-refresh impact assessment",
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Platform (e.g. net)")
    parser.add_argument("--content-root", type=Path, default=None)
    parser.add_argument("--knowledge-root", type=Path, default=None)
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Directory for page_impact.json output (default: reports/refresh_review/{family}/{platform}/)"
    )
    parser.add_argument("--json", action="store_true", help="Emit result JSON to stdout")
    parser.add_argument(
        "--require-delta", action="store_true",
        help="Exit 1 if knowledge_delta.json is absent (default: warn and continue)"
    )
    args = parser.parse_args(argv)

    kr = args.knowledge_root or (_REPO_ROOT / "knowledge")
    delta_path = kr / args.family / args.platform / "merged" / "knowledge_delta.json"
    if not delta_path.is_file():
        if args.require_delta:
            print(f"ERROR: knowledge_delta.json not found at {delta_path}", file=sys.stderr)
            return 1
        print(f"WARN: knowledge_delta.json not found at {delta_path}; all pages will score NOT_AFFECTED")

    result = assess_product(
        args.family,
        args.platform,
        content_root=args.content_root,
        knowledge_root=args.knowledge_root,
    )

    if args.output_dir:
        out_dir = args.output_dir
    else:
        out_dir = _REPO_ROOT / "reports" / "refresh_review" / args.family / args.platform

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "page_impact.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"PIA complete: {result['summary']['total']} pages assessed")
    print(f"  HIGH_IMPACT:            {result['summary']['HIGH_IMPACT']}")
    print(f"  MEDIUM_IMPACT:          {result['summary']['MEDIUM_IMPACT']}")
    print(f"  LOW_IMPACT:             {result['summary']['LOW_IMPACT']}")
    print(f"  NOT_AFFECTED:           {result['summary']['NOT_AFFECTED']}")
    print(f"  ENRICHMENT_CANDIDATES:  {result['enrichment_candidates_count']}")
    print(f"  Output: {out_path}")

    if args.json:
        sys.stdout.buffer.write(json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())