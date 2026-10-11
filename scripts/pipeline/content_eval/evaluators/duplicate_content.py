"""Duplicate content evaluator (RC-W1-005 / TC-BSA-05, MT026 blind-spot audit).

No evaluator in this registry previously detected duplicate or near-duplicate
*pages* (as opposed to duplicate *paragraphs* — see
``cross_page/deduplication.py``, which only runs opt-in via ``--cross-page``).
A real audit found 6 confirmed duplicate-content page pairs on cells/net
alone: pairs sharing an identical title, identical description/summary/
claims/apis, and a near-identical body, with the newer page's ``aliases:``
frontmatter pointing at the older page's real live slug — a URL-alias
collision. The same pattern (BLOG-URLDUPE-001) was previously found and
fixed once for note/python, but nothing in the pipeline prevented it from
recurring for cells/net.

This evaluator runs as part of the DEFAULT set (unlike cross_page/
deduplication.py) and checks two independent signals for every pair of
same-subdomain pages within one family/platform's blog and kb sections:

1. Similarity heuristic (category ``DP``): normalized title match plus a
   ``difflib.SequenceMatcher`` ratio over a title+description+summary+prose
   fingerprint. FAIL above a high body-similarity threshold, or when the
   title matches and body similarity clears a lower bar; WARN one tier down.
2. Alias collision (category ``AL``, always FAIL): a page's ``aliases``
   frontmatter list contains another live page's real rendered slug. This is
   a definite collision, not a heuristic — Hugo will build a redirect stub
   at a URL another page already owns.

Scope and performance: comparisons are confined to one (family, platform,
subdomain) group at a time (blog-vs-blog, kb-vs-kb — never cross-family or
cross-subdomain, and never sitewide), with a comparison cap and a cheap
Jaccard pre-filter before the more expensive SequenceMatcher call, matching
the bounded-cost approach already used by cross_page/deduplication.py.
"""

from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# sibling-import guard: content_discovery lives in scripts/pipeline/lib/, not
# on sys.path by default when this module is imported in isolation (e.g. by
# a test that never imported content_eval.loader first). Mirrors loader.py.
_HERE = Path(__file__).resolve().parent.parent.parent  # evaluators/ -> content_eval/ -> pipeline/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from content_discovery import discover_content  # noqa: E402

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_DUP_SUBDOMAINS = frozenset({"blog", "kb"})
_SUBDOMAIN_DIR = {"blog": "blog.aspose.org", "kb": "kb.aspose.org"}

_WORD_RE = re.compile(r"[a-z][a-z0-9']+")
_WS_RE = re.compile(r"\s+")
_SCHEME_HOST_RE = re.compile(r"^https?://[^/]+", re.IGNORECASE)

# Cheap word-set Jaccard floor a pair must clear before the more expensive
# SequenceMatcher ratio is computed at all.
_JACCARD_PREFILTER = 0.25

# Body-similarity (SequenceMatcher ratio) thresholds.
_FAIL_BODY = 0.85               # near-identical body regardless of title
_FAIL_BODY_WITH_TITLE = 0.60    # title matches + substantial body overlap
_WARN_BODY = 0.60               # high overlap even without a title match
_WARN_BODY_WITH_TITLE = 0.35    # title matches + moderate body overlap
_TITLE_NEAR_MATCH_RATIO = 0.90  # SequenceMatcher ratio treated as "same title"

# Bound worst-case cost within one (family, platform, subdomain) group.
_MAX_FINGERPRINT_CHARS = 20_000
_MAX_PAGES_PER_GROUP = 400
_MAX_COMPARISONS = 20_000


# ---------------------------------------------------------------------------
# Pure helpers — no disk I/O, directly unit-testable.
# ---------------------------------------------------------------------------

def _normalize_text(s: Any) -> str:
    if not s:
        return ""
    return _WS_RE.sub(" ", str(s).strip().lower())


def _title_of(page: Page) -> str:
    fm = page.frontmatter or {}
    return _normalize_text(fm.get("title"))


def _fingerprint(page: Page) -> str:
    """Build a normalized title+description+summary+headings+prose fingerprint."""
    fm = page.frontmatter or {}
    parts: list[str] = [
        str(fm.get("title") or ""),
        str(fm.get("description") or ""),
        str(fm.get("summary") or ""),
    ]
    parts.extend(h.text for h in page.headings)
    parts.extend(text for _, text in page.prose_lines)
    combined = " ".join(p for p in parts if p)
    return _normalize_text(combined)[:_MAX_FINGERPRINT_CHARS]


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _titles_match(title_a: str, title_b: str) -> bool:
    if not title_a or not title_b:
        return False
    if title_a == title_b:
        return True
    return SequenceMatcher(None, title_a, title_b).ratio() >= _TITLE_NEAR_MATCH_RATIO


def _compute_slug(page: Page) -> str:
    """Compute the page's rendered URL slug from its filesystem path.

    Mirrors the Hugo bundle/section rules used by dead_internal_link.py:
    ``_index.md``/``index.md`` render at their directory's depth; any other
    leaf ``.md`` file renders one segment deeper (its own stem).
    """
    parts = list(page.filepath.parts)
    anchor = None
    for i, p in enumerate(parts):
        if p.endswith(".aspose.org"):
            anchor = i
            break
    if anchor is None:
        return ""
    remaining = parts[anchor + 1:]
    if remaining and remaining[0] == "en":
        remaining = remaining[1:]
    if not remaining:
        return ""
    last = remaining[-1]
    if last in ("index.md", "_index.md"):
        slug_parts = list(remaining[:-1])
    else:
        stem = last[:-3] if last.endswith(".md") else last
        slug_parts = list(remaining[:-1]) + [stem]
    if not slug_parts:
        return "/"
    return ("/" + "/".join(slug_parts) + "/").lower()


def _normalize_alias(raw: Any) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    s = _SCHEME_HOST_RE.sub("", s)
    if not s:
        return ""
    if not s.startswith("/"):
        s = "/" + s
    s = re.sub(r"/{2,}", "/", s)
    s = re.sub(r"^/en/", "/", s, flags=re.IGNORECASE)
    if not s.endswith("/"):
        s = s + "/"
    return s.lower()


def _page_aliases(page: Page) -> set[str]:
    fm = page.frontmatter or {}
    raw = fm.get("aliases")
    if not raw:
        return set()
    if isinstance(raw, str):
        raw = [raw]
    return {norm for item in raw for norm in [_normalize_alias(item)] if norm}


def _alias_finding(owner_page: Page, target_page: Page, slug: str) -> Finding:
    return Finding(
        level="FAIL",
        category="AL",
        filepath=str(owner_page.filepath),
        line_no=1,
        message=(
            f"Alias collision: this page's `aliases` frontmatter claims `{slug}`, "
            f"which is the live rendered URL of {target_page.filepath} — two "
            f"distinct pages are claiming the same URL."
        ),
        suggestion=(
            "Remove the colliding alias entry, or merge/retire one of the two "
            "pages so only one page owns this URL."
        ),
        evaluator="duplicate_content",
    )


def _similarity_finding(subject_page: Page, other_page: Page, level: str, reason: str) -> Finding:
    return Finding(
        level=level,
        category="DP",
        filepath=str(subject_page.filepath),
        line_no=1,
        message=f"Duplicate/near-duplicate content vs {other_page.filepath}: {reason}.",
        suggestion=(
            "Consolidate these pages into one, meaningfully differentiate the "
            "content, or retire the older/duplicate page."
        ),
        evaluator="duplicate_content",
    )


def _check_alias_collision(a: dict, b: dict) -> list[Finding]:
    out: list[Finding] = []
    if b["slug"] and b["slug"] in a["aliases"]:
        out.append(_alias_finding(a["page"], b["page"], b["slug"]))
    if a["slug"] and a["slug"] in b["aliases"]:
        out.append(_alias_finding(b["page"], a["page"], a["slug"]))
    return out


def _check_similarity(a: dict, b: dict) -> list[Finding]:
    if str(a["page"].filepath) == str(b["page"].filepath):
        return []
    if _jaccard(a["tokens"], b["tokens"]) < _JACCARD_PREFILTER:
        return []

    ratio = SequenceMatcher(None, a["fp"], b["fp"]).ratio()
    title_match = _titles_match(a["title"], b["title"])

    if ratio >= _FAIL_BODY:
        level, reason = "FAIL", f"near-identical body (similarity={ratio:.2f})"
    elif title_match and ratio >= _FAIL_BODY_WITH_TITLE:
        level, reason = "FAIL", f"identical/near-identical title with overlapping body (similarity={ratio:.2f})"
    elif ratio >= _WARN_BODY:
        level, reason = "WARN", f"high body overlap (similarity={ratio:.2f})"
    elif title_match and ratio >= _WARN_BODY_WITH_TITLE:
        level, reason = "WARN", f"identical/near-identical title with moderate body overlap (similarity={ratio:.2f})"
    else:
        return []

    return [_similarity_finding(a["page"], b["page"], level, reason)]


def find_duplicate_pairs(pages: list[Page]) -> list[Finding]:
    """Compare every pair of *pages* and return duplicate/alias-collision findings.

    Pure function — no disk I/O. Pairs are only ever emitted once, attributed
    to whichever of the two pages sorts first by filepath, so callers may run
    this once per page in a batch without double-counting (see
    ``DuplicateContentEvaluator.evaluate``, which additionally caches the
    result per (family, platform, subdomain) group).
    """
    findings: list[Finding] = []
    if len(pages) < 2:
        return findings

    ordered = sorted(pages, key=lambda p: str(p.filepath))[:_MAX_PAGES_PER_GROUP]

    infos = []
    for p in ordered:
        fp = _fingerprint(p)
        infos.append({
            "page": p,
            "title": _title_of(p),
            "fp": fp,
            "tokens": _tokens(fp),
            "slug": _compute_slug(p),
            "aliases": _page_aliases(p),
        })

    comparisons = 0
    n = len(infos)
    for i in range(n):
        a = infos[i]
        for j in range(i + 1, n):
            comparisons += 1
            if comparisons > _MAX_COMPARISONS:
                return findings
            b = infos[j]
            findings.extend(_check_alias_collision(a, b))
            findings.extend(_check_similarity(a, b))

    return findings


# ---------------------------------------------------------------------------
# Disk-scanning glue — group discovery + per-process caches.
# ---------------------------------------------------------------------------

_DISCOVER_CACHE: dict[tuple[str, str], list[Path]] = {}
_FINDINGS_CACHE: dict[tuple[str, str, str], list[Finding]] = {}


def _reset_caches() -> None:
    """Test-only: clear per-process caches between isolated test runs."""
    _DISCOVER_CACHE.clear()
    _FINDINGS_CACHE.clear()


def _discover_family_platform(family: str, platform: str) -> list[Path]:
    key = (family, platform)
    if key not in _DISCOVER_CACHE:
        _DISCOVER_CACHE[key] = discover_content(family, platform)
    return _DISCOVER_CACHE[key]


def _load_group(family: str, platform: str, subdomain: str) -> list[Page]:
    site_dir_name = _SUBDOMAIN_DIR.get(subdomain)
    if not site_dir_name:
        return []
    files = _discover_family_platform(family, platform)
    matching = [f for f in files if site_dir_name in f.parts]
    pages: list[Page] = []
    for f in matching:
        try:
            pages.append(Page.load(f))
        except (OSError, UnicodeDecodeError):
            continue
    return pages


class DuplicateContentEvaluator(BaseEvaluator):
    """Flags duplicate/near-duplicate pages and alias-slug collisions.

    Scoped to one (family, platform, subdomain) group at a time — blog pages
    are only compared against other blog pages in the same family/platform,
    kb pages only against other kb pages. Never sitewide, never cross-family.
    """

    name = "duplicate_content"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if page.subdomain not in _DUP_SUBDOMAINS or not page.family or not page.platform:
            return []

        key = (page.family, page.platform, page.subdomain)
        if key not in _FINDINGS_CACHE:
            group = _load_group(page.family, page.platform, page.subdomain)
            _FINDINGS_CACHE[key] = find_duplicate_pairs(group) if len(group) > 1 else []

        this_path = str(page.filepath)
        return [f for f in _FINDINGS_CACHE[key] if f.filepath == this_path]
