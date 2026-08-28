"""backlink_targets.py — Shared library for aspose.org → aspose.com reciprocal backlink resolution.

Public API:
    load_target_map(repo_root)              — Load data/aspose_com_targets.json
    classify_page_type(source_path)         — Classify page by §Q.3 table
    resolve_backlink(family, platform, source_subdomain, target_map, *, exact_deep_match_enabled)
    count_qualifying_com_links(body_text)   — Count *.aspose.com/* links in body (strips code fences)
    classify_compliance(...)                — Return MISSING|COMPLIANT|WRONG_TARGET|OVER_LIMIT|BLOCKED_TARGET|SKIPPED

All functions that return structured results use the ResolutionRecord dataclass.
This library never raises on expected error paths — always returns a record.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]

# ── Constants ─────────────────────────────────────────────────────────────────

KNOWN_FAMILIES = {
    "3d", "barcode", "cad", "cells", "diagram", "drawing", "email", "finance",
    "font", "gis", "html", "imaging", "medical", "note", "ocr", "omr", "page",
    "pdf", "psd", "pub", "slides", "svg", "tasks", "tex", "words", "zip",
}

# Canonical platform-alias table (TC5, 2026-08-21). This is the SINGLE definition
# for the whole backlink pipeline -- fetch_aspose_com_targets.py imports it from
# here rather than keeping its own copy. Before this fix, that file had an
# independent, smaller table missing python-cpp/go-cpp/nodejs-cpp/javascript-cpp/
# php/php-java/jasperreports/rust-cpp, which silently classified real, live
# HTTP-200 platforms (e.g. reference.aspose.com/pdf/python-cpp/) as "unknown" and
# dropped them from the structured target map. "rs" (short for rust) is the one
# alias fetch_aspose_com_targets.py had that this table lacked -- folded in below
# so the union is complete in both directions, not just this file's superset.
PLATFORM_ALIASES: dict[str, str] = {
    "net": "net", "dotnet": "net", "csharp": "net", "net60": "net", "net48": "net", "net40": "net",
    "python": "python", "py": "python", "python3": "python", "python-net": "python",
    "python-java": "python", "python-cpp": "python",
    "java": "java", "java8": "java", "java11": "java", "java-android": "java",
    "cpp": "cpp", "c-plus-plus": "cpp", "cplusplus": "cpp", "c++": "cpp",
    "nodejs": "nodejs", "node": "nodejs", "node-js": "nodejs", "javascript": "nodejs", "js": "nodejs",
    "nodejs-net": "nodejs", "nodejs-java": "nodejs", "nodejs-cpp": "nodejs", "javascript-cpp": "nodejs",
    "android": "android", "android-java": "android", "androidjava": "android",
    "cloud": "cloud", "rest-api": "cloud", "api": "cloud", "saas": "cloud",
    "ruby": "ruby", "ruby-net": "ruby",
    "go": "go", "golang": "go", "go-cpp": "go",
    "php": "php", "php-java": "php",
    "typescript": "typescript",
    # Enterprise-only bridge slugs (no local aspose.org equivalent)
    "jasperreports": "jasperreports",
    "rust": "rust", "rust-cpp": "rust", "rs": "rust",
}

LOCALE_CODES = {
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
}

# Locale suffix: index.de.md, archive.fr.md
LOCALE_RE = re.compile(r'\.(?:' + '|'.join(LOCALE_CODES) + r')\.md$')

# *.aspose.com/* link pattern (§2.2)
COM_LINK_RE = re.compile(r'https?://[a-z0-9.-]+\.aspose\.com/[^\s"\')\]]*', re.IGNORECASE)

# Subdomains that are NOT qualifying enterprise product links (community/support only)
NON_QUALIFYING_COM_HOSTS: frozenset[str] = frozenset([
    "forum.aspose.com",
])

# Code fence detection
CODE_FENCE_RE = re.compile(r'```.*?```', re.DOTALL)
INLINE_CODE_RE = re.compile(r'`[^`]+`')


# ── Page type enum (§Q.3) ─────────────────────────────────────────────────────

class PageType(str, Enum):
    # Docs
    DOCS_FAMILY_INDEX    = "docs-family-index"
    DOCS_PLATFORM_INDEX  = "docs-platform-index"
    DOCS_CATEGORY_TOC    = "docs-category-toc"
    DOCS_ARTICLE         = "docs-article"
    # KB
    KB_FAMILY_INDEX      = "kb-family-index"
    KB_PLATFORM_INDEX    = "kb-platform-index"
    KB_ARTICLE           = "kb-article"
    # Reference
    REF_FAMILY_INDEX     = "reference-family-index"
    REF_PLATFORM_INDEX   = "reference-platform-index"
    REF_CLASS            = "reference-class"
    REF_NESTED_CLASS     = "reference-nested-class"
    # Products
    PRODUCTS_ROOT        = "products-root"
    PRODUCTS_FAMILY      = "products-family"
    PRODUCTS_PLUGIN      = "products-plugin"
    # Blog
    BLOG_POST            = "blog-post"
    BLOG_ARCHIVE         = "blog-archive"
    BLOG_PLATFORM_INDEX  = "blog-platform-index"
    # Out of scope / skip
    SUBDOMAIN_ROOT       = "subdomain-root"
    BLOG_UTILITY         = "blog-utility"
    LOCALE_FILE          = "locale-file"
    LOCALE_DIR           = "locale-dir"
    # Unknown
    UNKNOWN_PATTERN      = "UNKNOWN_PATTERN"


# ── Compliance statuses ───────────────────────────────────────────────────────

MISSING         = "MISSING"
COMPLIANT       = "COMPLIANT"
WRONG_TARGET    = "WRONG_TARGET"
OVER_LIMIT      = "OVER_LIMIT"
BLOCKED_TARGET  = "BLOCKED_TARGET"
SKIPPED         = "SKIPPED"
# P0 A2: page uses a family-level link when a verified platform-level target exists
FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE = "FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE"
# TC2 (2026-08-21): correct target URL, but the anchor text doesn't match the
# governed registry wording -- the exact defect class that let "commercial
# edition" survive indefinitely on products.aspose.org/cells, since the old
# URL-only classification treated it as COMPLIANT forever.
WRONG_ANCHOR_TEXT = "WRONG_ANCHOR_TEXT"
# TC2 (2026-08-21): 2 distinct qualifying URLs both individually "acceptable"
# (e.g. both the family-level AND platform-level link present at once) --
# previously silently classified COMPLIANT because the old check only asked
# "is ANY existing URL acceptable," never "are there redundant ones."
DUPLICATE_LINK = "DUPLICATE_LINK"
# TC10 (2026-08-21): 2+ distinct qualifying URLs present, but they don't span
# distinct aspose.com hosts (e.g. two different products.aspose.com URLs) --
# the user's own diversity requirement ("those links must be from different
# subdomains on aspose.com"). Distinct from DUPLICATE_LINK, which is the more
# specific family+platform-fallback-chain redundancy case (checked first);
# this catches any other same-host pairing DUPLICATE_LINK doesn't cover, e.g.
# an acceptable link plus an unrelated WRONG_TARGET link on the same host.
# Previously: "a page with two links, both to products.aspose.com, passes as
# fully COMPLIANT today" (confirmed live) -- the old single-URL-match loop
# below returned COMPLIANT on the first acceptable URL without ever checking
# whether a sibling link shared its host.
DUPLICATE_SUBDOMAIN = "DUPLICATE_SUBDOMAIN"

# A7-03: KB anchor transition statuses (LEGACY_COMPAT_MODE vs CANONICAL_POST_P0_MODE)
ACCEPTABLE_LEGACY_KB_PRE_P0     = "ACCEPTABLE_LEGACY_KB_PRE_P0"
CANONICAL_KB_POST_P0            = "CANONICAL_KB_POST_P0"
UPGRADE_CANDIDATE_NOT_YET_FIXED = "UPGRADE_CANDIDATE_NOT_YET_FIXED"

# A7-03: KB anchor transition mode names
LEGACY_COMPAT_MODE      = "LEGACY_COMPAT_MODE"
CANONICAL_POST_P0_MODE  = "CANONICAL_POST_P0_MODE"

# A3: Resolution kind identifiers
class ResolutionKind:
    EXACT_VERIFIED             = "EXACT_VERIFIED"
    APPROVED_DEEP_AUTHORITY    = "APPROVED_DEEP_AUTHORITY"
    PLATFORM_CANONICAL         = "PLATFORM_CANONICAL"
    BEST_VERIFIED_ANCESTOR     = "BEST_VERIFIED_ANCESTOR"
    FAMILY_FALLBACK            = "FAMILY_FALLBACK"
    ROOT_FALLBACK              = "ROOT_FALLBACK"
    BLOCKED_NO_VERIFIED_TARGET = "BLOCKED_NO_VERIFIED_TARGET"
    AMBIGUOUS_PLATFORM_TARGETS = "AMBIGUOUS_PLATFORM_TARGETS"
    AUTHORITY_STALE_FALLBACK   = "AUTHORITY_STALE_FALLBACK"

# A3: Ancestor fallback audit status constants
EXACT_VERIFIED_TARGET           = "EXACT_VERIFIED_TARGET"
ANCESTOR_FALLBACK_USED          = "ANCESTOR_FALLBACK_USED"
PLATFORM_FALLBACK_USED          = "PLATFORM_FALLBACK_USED"
FAMILY_FALLBACK_USED            = "FAMILY_FALLBACK_USED"
ROOT_FALLBACK_USED              = "ROOT_FALLBACK_USED"
NO_VERIFIED_FALLBACK            = "NO_VERIFIED_FALLBACK"
SKIPPED_CLOSER_VERIFIED_PARENT  = "SKIPPED_CLOSER_VERIFIED_PARENT"
UNVERIFIED_CHILD_TARGET_BLOCKED = "UNVERIFIED_CHILD_TARGET_BLOCKED"

# A5-L6 Source-type policy statuses (STRUCTURAL_PAGE_SKIP, DEFERRED_NO_TARGETS)
# removed TC13 (2026-08-26): both were dead code, referenced nowhere in
# scripts/ outside their own definition (confirmed by repo-wide grep before
# removal). A page-type-level bulk exemption was never a legitimate design
# here: the closest real "structural" candidate in this codebase -- the
# family/platform index pages this same TC13 pass added backlink coverage
# for -- is explicitly IN scope for a backlink, not exempt from one. The
# one legitimate opt-out path is the existing per-page `backlink_scope:
# exempt` frontmatter field (see _check_backlink_exemption() in
# backlink_backfill.py) -- explicit, reasoned, time-bounded, and already
# wired in; it cannot accidentally blanket-exempt an entire page type the
# way reviving a type-level skip status would.

# A4: Variant authority audit statuses
EXACT_PLATFORM_VERIFIED              = "EXACT_PLATFORM_VERIFIED"
VARIANT_CANONICAL_SELECTED           = "VARIANT_CANONICAL_SELECTED"
VARIANT_REVIEW_REQUIRED              = "VARIANT_REVIEW_REQUIRED"
VARIANT_BLOCKED_NO_POLICY            = "VARIANT_BLOCKED_NO_POLICY"
ANCESTOR_FALLBACK_AFTER_NO_VARIANT   = "ANCESTOR_FALLBACK_AFTER_NO_VARIANT"
VARIANT_CANDIDATES_NOT_IN_MAP        = "VARIANT_CANDIDATES_NOT_IN_MAP"
SITEMAP_COVERAGE_GAP                 = "SITEMAP_COVERAGE_GAP"
MULTIPLE_VARIANTS_REQUIRES_REVIEW    = "MULTIPLE_VARIANTS_REQUIRES_REVIEW"

# A5-L5: Conflict resolution audit statuses
CONFLICT_RESOLVED_BY_TIER1           = "CONFLICT_RESOLVED_BY_TIER1"
CONFLICT_RESOLVED_BY_AI_ASSIST       = "CONFLICT_RESOLVED_BY_AI_ASSIST"
CONFLICT_ESCALATED_TO_OPERATOR       = "CONFLICT_ESCALATED_TO_OPERATOR"
CONFLICT_ANCHOR_AUTO_CORRECTED       = "CONFLICT_ANCHOR_AUTO_CORRECTED"
CONFLICT_NAMESPACE_MISMATCH_BLOCKED  = "CONFLICT_NAMESPACE_MISMATCH_BLOCKED"

# A9 (L9): AI status constants
AI_ENRICHED_PRIMARY         = "AI_ENRICHED_PRIMARY"
AI_ENRICHED_FALLBACK        = "AI_ENRICHED_FALLBACK"
AI_UNAVAILABLE_DEGRADED     = "AI_UNAVAILABLE_DEGRADED"
AI_EXPLICITLY_DISABLED      = "AI_EXPLICITLY_DISABLED"
AI_DEGRADATION_RATE_WARNING = "AI_DEGRADATION_RATE_WARNING"


# ── Subdomain content roots ───────────────────────────────────────────────────

SUBDOMAIN_ROOTS = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
}

# Preferred reciprocal subdomain per source (§4.1)
PREFERRED_TARGET_SUBDOMAIN = {
    "docs.aspose.org":      "docs.aspose.com",
    "kb.aspose.org":        "kb.aspose.com",
    "reference.aspose.org": "reference.aspose.com",
    "products.aspose.org":  "products.aspose.com",
    "blog.aspose.org":      "blog.aspose.com",
}

# A3: Host map for URL composition — ONLY used in resolve_best_verified_ancestor() / _resolve_deep()
HOST_MAP: dict = {
    "docs":      "docs.aspose.com",
    "kb":        "kb.aspose.com",
    "products":  "products.aspose.com",
    "reference": "reference.aspose.com",
    "blog":      "blog.aspose.com",
}

# A3: Source subdomain → HOST_MAP prefix key
SOURCE_TO_TARGET_PREFIX: dict = {
    "docs.aspose.org":      "docs",
    "kb.aspose.org":        "kb",
    "reference.aspose.org": "reference",
    "products.aspose.org":  "products",
    "blog.aspose.org":      "blog",
}

# TC7 (2026-08-21): target host -> HOST_MAP prefix key (the reverse of
# HOST_MAP itself). Needed because resolve_backlink()'s preferred_sd is a
# host ("reference.aspose.com") but platform_variant_authority.json's
# request_key format uses the short prefix ("reference/pdf/python").
TARGET_HOST_TO_PREFIX: dict = {v: k for k, v in HOST_MAP.items()}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ResolutionRecord:
    source_file: str
    source_url: str
    subdomain: str
    family: Optional[str]
    platform: Optional[str]
    page_type: PageType
    existing_com_links: list[str] = field(default_factory=list)
    existing_com_link_count: int = 0
    chosen_target_url: Optional[str] = None
    chosen_target_type: Optional[str] = None
    chosen_target_subdomain: Optional[str] = None
    fallback_reason: Optional[str] = None
    status: str = MISSING
    warning_messages: list[str] = field(default_factory=list)
    resolution_evidence: str = ""


@dataclass
class AncestorResolutionResult:
    """Result of resolve_best_verified_ancestor(). Pure data — no I/O."""
    requested_path: str
    selected_path: Optional[str]
    selected_url: Optional[str]
    resolution_kind: str
    fallback_depth: int           # 0=exact, 1=one level up, -1=blocked
    fallback_chain: list          # [{path, status, url}, ...]
    fallback_reason: Optional[str]
    root_fallback_used: bool
    verified: bool


# ── Target map loading ────────────────────────────────────────────────────────

def load_target_map(repo_root: "Path | str | None" = None) -> dict:
    """
    Load data/aspose_com_targets.json.
    Raises FileNotFoundError if missing, json.JSONDecodeError if corrupt.
    """
    root = Path(repo_root) if repo_root else _REPO_ROOT
    path = root / "data" / "aspose_com_targets.json"
    if not path.exists():
        raise FileNotFoundError(f"Target map not found: {path}. Run fetch_aspose_com_targets.py first.")
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if "targets" not in data:
        raise ValueError(f"Target map missing 'targets' key: {path}")
    return data


def target_map_age_days(target_map: dict, *, now: "datetime.datetime | None" = None) -> "float | None":
    """
    Age in days of target_map['provenance']['generated_at'], or None if the
    field is missing/unparseable.

    Added 2026-08-06 (MT022 TC-03): `provenance.generated_at` was written by
    fetch_aspose_com_targets.py on every run but read by zero consumers --
    confirmed live: a redirect-bug-fix commit (e40ed6b509) found 5 entries had
    silently gone stale/dead over 6 weeks with nothing noticing, because
    nothing anywhere checked this field. This is the read half of that gap;
    callers decide what to do with the age (warn, gate, report) -- this
    function only computes it, matching load_target_map's own no-side-effects
    contract.
    """
    import datetime as _datetime

    generated_at = target_map.get("provenance", {}).get("generated_at")
    if not generated_at:
        return None
    try:
        generated_dt = _datetime.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    now = now or _datetime.datetime.now(_datetime.timezone.utc)
    if generated_dt.tzinfo is None:
        generated_dt = generated_dt.replace(tzinfo=_datetime.timezone.utc)
    return (now - generated_dt).total_seconds() / 86400.0


# Thresholds for target_map_age_days() consumers (MT022 TC-03). WARN is
# advisory (content generation logs and proceeds); BLOCK is the harder
# threshold a CI-style gate should fail on -- deliberately not wired into a
# hard-fail here, since load_target_map()/this module never raises on
# freshness (only on missing/corrupt data), matching its documented contract.
STALE_WARN_DAYS = 14
STALE_BLOCK_DAYS = 30


# ── Page type classification (§Q.3) ──────────────────────────────────────────

def classify_page_type(
    source_path: "Path | str",
    repo_root: "Path | str | None" = None,
) -> tuple[PageType, Optional[str], Optional[str], str]:
    """
    Classify a source file by §Q.3 page type table.
    Returns (page_type, family, platform, subdomain).

    Never raises — returns UNKNOWN_PATTERN on any unrecognized structure.
    """
    path = Path(source_path)
    root = Path(repo_root) if repo_root else _REPO_ROOT

    # Determine which subdomain this file belongs to
    subdomain: Optional[str] = None
    rel_to_en_root: Optional[Path] = None

    for sd, sd_root_rel in SUBDOMAIN_ROOTS.items():
        sd_root = root / sd_root_rel
        try:
            rel = path.relative_to(sd_root)
            subdomain = sd
            rel_to_en_root = rel
            break
        except ValueError:
            continue

    if subdomain is None or rel_to_en_root is None:
        return PageType.UNKNOWN_PATTERN, None, None, ""

    parts = list(rel_to_en_root.parts)
    filename = parts[-1]
    dir_parts = parts[:-1]
    dc = len(dir_parts)

    # Locale file check (suffix-based)
    if LOCALE_RE.search(filename):
        return PageType.LOCALE_FILE, None, None, subdomain

    family = dir_parts[0] if dc >= 1 and dir_parts[0] in KNOWN_FAMILIES else None
    raw_platform = dir_parts[1] if dc >= 2 else None
    platform = PLATFORM_ALIASES.get(raw_platform or "") if raw_platform else None

    # Blog locale dir check
    if subdomain == "blog.aspose.org" and dc >= 1 and dir_parts[0] in LOCALE_CODES:
        return PageType.LOCALE_DIR, None, None, subdomain

    # Out-of-scope root files
    if dc == 0 and filename == "_index.md" and subdomain != "products.aspose.org":
        return PageType.SUBDOMAIN_ROOT, None, None, subdomain

    # ── Blog ──────────────────────────────────────────────────────────────
    if subdomain == "blog.aspose.org":
        if re.match(r'^archive', filename):
            return PageType.BLOG_ARCHIVE, None, None, subdomain
        if dc == 0:
            return PageType.BLOG_UTILITY, None, None, subdomain
        # TC13 (2026-08-26): platform-level blog index page
        # (content/blog.aspose.org/{family}/{platform}/_index.md, e.g.
        # words/python/_index.md), created by new-blog-index.md -- this
        # branch was previously missing entirely, so this page shape fell
        # through to UNKNOWN_PATTERN, which IS in OUT_OF_SCOPE_TYPES: the
        # page was structurally invisible to backlink_audit.py, not merely
        # unimplemented in the creation skill. No family-level blog index
        # exists anywhere in the tree today (new-blog-index.md only ever
        # creates the platform-level file), so no dc==1 branch is added.
        if dc == 2 and filename == "_index.md":
            return PageType.BLOG_PLATFORM_INDEX, family, platform, subdomain
        if dc == 3 and filename == "index.md":
            return PageType.BLOG_POST, family, platform, subdomain
        return PageType.UNKNOWN_PATTERN, family, platform, subdomain

    # ── Docs ──────────────────────────────────────────────────────────────
    if subdomain == "docs.aspose.org":
        if dc == 1 and filename == "_index.md":
            return PageType.DOCS_FAMILY_INDEX, family, None, subdomain
        if dc == 2 and filename == "_index.md":
            return PageType.DOCS_PLATFORM_INDEX, family, platform, subdomain
        if dc == 3 and filename == "_index.md":
            return PageType.DOCS_CATEGORY_TOC, family, platform, subdomain
        if dc == 3 and filename.endswith(".md"):
            return PageType.DOCS_ARTICLE, family, platform, subdomain
        if dc == 2 and filename.endswith(".md"):
            return PageType.DOCS_ARTICLE, family, platform, subdomain
        return PageType.UNKNOWN_PATTERN, family, platform, subdomain

    # ── KB ────────────────────────────────────────────────────────────────
    if subdomain == "kb.aspose.org":
        if dc == 1 and filename == "_index.md":
            return PageType.KB_FAMILY_INDEX, family, None, subdomain
        if dc == 2 and filename == "_index.md":
            return PageType.KB_PLATFORM_INDEX, family, platform, subdomain
        if dc == 2 and filename.endswith(".md"):
            return PageType.KB_ARTICLE, family, platform, subdomain
        return PageType.UNKNOWN_PATTERN, family, platform, subdomain

    # ── Reference ─────────────────────────────────────────────────────────
    if subdomain == "reference.aspose.org":
        if dc == 1 and filename == "_index.md":
            return PageType.REF_FAMILY_INDEX, family, None, subdomain
        if dc == 2 and filename == "_index.md":
            return PageType.REF_PLATFORM_INDEX, family, platform, subdomain
        if dc == 2 and filename.endswith(".md"):
            return PageType.REF_CLASS, family, platform, subdomain
        if dc == 3 and filename.endswith(".md"):
            return PageType.REF_NESTED_CLASS, family, platform, subdomain
        # depth-5+ → UNKNOWN_PATTERN
        return PageType.UNKNOWN_PATTERN, family, platform, subdomain

    # ── Products ──────────────────────────────────────────────────────────
    if subdomain == "products.aspose.org":
        if dc == 0 and filename == "_index.md":
            return PageType.PRODUCTS_ROOT, None, None, subdomain
        if dc == 1 and filename == "_index.md":
            return PageType.PRODUCTS_FAMILY, family, None, subdomain
        if dc == 2 and filename == "_index.md":
            return PageType.PRODUCTS_PLUGIN, family, platform, subdomain
        return PageType.UNKNOWN_PATTERN, family, platform, subdomain

    return PageType.UNKNOWN_PATTERN, family, platform, subdomain


# ── Resolution algorithm (§4.2 + §Q.4 default fallback matrix) ───────────────

def _lookup_platform(target_map: dict, subdomain: str, family: str, platform: str) -> Optional[str]:
    """Look up platform-level URL in target map. Returns URL if http_status==200, else None."""
    key = f"{family}/{platform}"
    entry = target_map.get("targets", {}).get(subdomain, {}).get("platforms", {}).get(key)
    if entry and entry.get("http_status") == 200:
        return entry.get("url")
    # A9: Fallback to all_urls when targets entry is stale or missing
    fallback_url = f"https://{subdomain}/{family}/{platform}/"
    all_entry = target_map.get("all_urls", {}).get(fallback_url)
    if all_entry and all_entry.get("http_status") == 200:
        return fallback_url
    return None


def _lookup_family(target_map: dict, subdomain: str, family: str) -> Optional[str]:
    """Look up family-level URL in target map. Returns URL if http_status==200, else None."""
    entry = target_map.get("targets", {}).get(subdomain, {}).get("families", {}).get(family)
    if entry and entry.get("http_status") == 200:
        return entry.get("url")
    # A9: Fallback to all_urls when targets entry is stale or missing
    fallback_url = f"https://{subdomain}/{family}/"
    all_entry = target_map.get("all_urls", {}).get(fallback_url)
    if all_entry and all_entry.get("http_status") == 200:
        return fallback_url
    return None


# ── A3: Ancestor fallback functions ──────────────────────────────────────────

def build_ancestor_chain(full_path: str) -> list:
    """
    Build ancestor chain from most-specific to least-specific.
    full_path: e.g. "docs/cells/python/developer-guide"
    Returns: ["docs/cells/python/developer-guide", "docs/cells/python", "docs/cells", "docs"]

    The last entry is always the single-segment subdomain prefix.
    Pure function. No I/O.
    """
    segments = full_path.strip("/").split("/")
    return ["/".join(segments[:i]) for i in range(len(segments), 0, -1)]


def _compose_ancestor_url(path: str) -> Optional[str]:
    """
    Compose full URL from a path-only key using HOST_MAP.
    path "docs/cells/python" → "https://docs.aspose.com/cells/python/"
    path "docs" (root)       → "https://docs.aspose.com/"
    Returns None if first segment not in HOST_MAP.
    """
    parts = path.strip("/").split("/")
    prefix = parts[0] if parts else ""
    host = HOST_MAP.get(prefix)
    if not host:
        return None
    if len(parts) == 1:
        return f"https://{host}/"
    rest = "/".join(parts[1:])
    return f"https://{host}/{rest}/"


def resolve_best_verified_ancestor(
    full_path: str,
    target_map: dict,
    *,
    allowed_root_fallback: bool = True,
    policy_context: Optional[dict] = None,
) -> AncestorResolutionResult:
    """
    Walk ancestor chain from most-specific to least-specific.
    Returns the first ancestor whose full URL appears in target_map["all_urls"] with http_status==200.

    Pure function. No I/O. No HTTP. No LLM.

    full_path: path-only with HOST_MAP prefix as first segment.
      e.g. "docs/cells/python/developer-guide" or "kb/cells/java/article-slug"
    allowed_root_fallback: if False, blocks selection of the single-segment root.
    """
    chain = build_ancestor_chain(full_path)
    all_urls = target_map.get("all_urls", {})
    fallback_chain: list = []

    for depth, path in enumerate(chain):
        url = _compose_ancestor_url(path)
        if url is None:
            fallback_chain.append({"path": path, "status": "invalid_prefix", "url": None})
            continue

        is_root = (len(path.strip("/").split("/")) == 1)

        # Block root if not allowed
        if is_root and depth > 0 and not allowed_root_fallback:
            fallback_chain.append({"path": path, "status": "root_fallback_blocked", "url": url})
            continue

        entry = all_urls.get(url)
        if entry and entry.get("http_status") == 200:
            fallback_chain.append({"path": path, "status": "verified_200", "url": url})
            if depth == 0:
                kind = ResolutionKind.EXACT_VERIFIED
            elif is_root:
                kind = ResolutionKind.ROOT_FALLBACK
            else:
                kind = ResolutionKind.BEST_VERIFIED_ANCESTOR
            return AncestorResolutionResult(
                requested_path=full_path,
                selected_path=path,
                selected_url=url,
                resolution_kind=kind,
                fallback_depth=depth,
                fallback_chain=fallback_chain,
                fallback_reason=None if depth == 0 else "exact_child_not_in_all_urls",
                root_fallback_used=(is_root and depth > 0),
                verified=True,
            )
        else:
            status = "missing_or_unverified" if entry is None else f"http_{entry.get('http_status', 'unknown')}"
            fallback_chain.append({"path": path, "status": status, "url": url})

    # No ancestor verified
    return AncestorResolutionResult(
        requested_path=full_path,
        selected_path=None,
        selected_url=None,
        resolution_kind=ResolutionKind.BLOCKED_NO_VERIFIED_TARGET,
        fallback_depth=-1,
        fallback_chain=fallback_chain,
        fallback_reason="no_verified_ancestor_in_all_urls",
        root_fallback_used=False,
        verified=False,
    )


def _resolve_deep(
    authority: dict,
    source_file: str,
) -> Optional[tuple]:
    """
    Look up source_file in deep backlink authority (Layer 3).

    Returns (url, type, subdomain, None) if a valid approved deep target exists,
    or None to fall back to v1 resolution.

    Checks (in order):
      1. source_file present in authority["authority"]
      2. allowed_for_generation: true
      3. anchor_config_hash matches active config (if registry available)
      4. Compose URL via HOST_MAP[target_subdomain]/target_path/

    Never reads Layer 1 or Layer 2. No HTTP calls. No LLM calls.
    """
    auth_records = authority.get("authority", {})
    # Normalize path separators — authority keys may use \ (Windows) or / (POSIX)
    record = auth_records.get(source_file)
    if record is None:
        alt_key = source_file.replace("/", "\\")
        record = auth_records.get(alt_key)
    if record is None:
        return None

    if not record.get("allowed_for_generation", False):
        return None

    target_subdomain = record.get("target_subdomain")
    target_path = record.get("target_path", "")
    if not target_subdomain or not target_path:
        return None

    host = HOST_MAP.get(target_subdomain)
    if not host:
        return None

    # Check anchor config hash staleness if registry is accessible
    stored_hash = record.get("anchor_config_hash")
    if stored_hash:
        try:
            active_hash = compute_anchor_config_hash()
            if active_hash != stored_hash:
                # Anchor config has changed — authority record is stale
                return None
        except Exception:
            pass  # Registry unavailable — proceed without hash check

    url = f"https://{host}/{target_path.strip('/')}/"
    return url, "platform", target_subdomain, None


def resolve_backlink(
    family: Optional[str],
    platform: Optional[str],
    source_subdomain: str,
    target_map: dict,
    *,
    exact_deep_match_enabled: bool = False,
    canonical_overrides: Optional[dict] = None,
    authority: Optional[dict] = None,
    source_file: Optional[str] = None,
    variant_authority: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve the best backlink target URL per §Q.4 default fallback matrix.
    Returns (chosen_url, chosen_type, chosen_subdomain, fallback_reason).
    chosen_url is None on BLOCKED_TARGET, also None when
    chosen_type == ResolutionKind.AMBIGUOUS_PLATFORM_TARGETS (routes to S-90,
    not bot-executable -- see variant_authority below).

    exact_deep_match_enabled: If True, consult deep backlink authority (Layer 3).
    Default is False per §J.1 — v1 behavior is byte-identical when False.

    canonical_overrides: Optional dict loaded from platform_canonical_overrides.yaml.
    Only entries with http_verified: true are applied. (A2 P0)

    authority: Layer 3 approved backlink authority dict (loaded from backlink_authority.json).
    source_file: Repo-relative path of the source content file for authority lookup.

    variant_authority: (TC7, 2026-08-21) optional dict from load_variant_authority(),
    keyed by request_key ("{prefix}/{family}/{local_platform}"). When a
    REVIEW_REQUIRED record exists for this (family, platform) on the resolved
    target subdomain, resolution stops and returns AMBIGUOUS_PLATFORM_TARGETS
    instead of silently picking a candidate via alias-table order. Omitting
    this parameter (the default) preserves prior behavior exactly -- opt-in,
    backward compatible, matching every other Layer-0.5+ enrichment param above.
    """
    if not family:
        return None, None, None, "no family detected"

    # Step 1: Deep authority lookup (opt-in only, default disabled)
    if exact_deep_match_enabled and authority and source_file:
        deep_result = _resolve_deep(authority, source_file)
        if deep_result:
            return deep_result

    preferred_sd = PREFERRED_TARGET_SUBDOMAIN.get(source_subdomain, "products.aspose.com")

    # D1 FIX: blog.aspose.org uses ancestor chain resolution because blog.aspose.com
    # has no family/platform structured landing pages (only root at https://blog.aspose.com/).
    # resolve_best_verified_ancestor() walks: blog/pdf/net → blog/pdf → blog/
    # The root https://blog.aspose.com/ is HTTP 200 in all_urls, so ROOT_FALLBACK is guaranteed.
    if source_subdomain == "blog.aspose.org":
        path_parts = ["blog"]
        if family:
            path_parts.append(family)
        if platform:
            path_parts.append(platform)
        ancestor_path = "/".join(path_parts)
        ancestor_result = resolve_best_verified_ancestor(
            ancestor_path, target_map, allowed_root_fallback=True
        )
        if ancestor_result.selected_url:
            # ROOT_FALLBACK has no platform match — always treat as "family" type
            ttype = "family"
            return (
                ancestor_result.selected_url,
                ttype,
                "blog.aspose.com",
                ancestor_result.fallback_reason,
            )
        return None, None, None, f"no blog.aspose.com ancestor found for {family}/{platform}"

    if platform:
        # TC7 (2026-08-21): Check the variant authority BEFORE the plain platform
        # lookup / canonical override. A REVIEW_REQUIRED record means Layer 0.6
        # (backlink_build_platform_variant_authority.py) already found 2+ live,
        # HTTP-verified candidate platform slugs for this (family, local platform)
        # pair with no canonical rule to pick between them (e.g. reference.aspose.com's
        # pdf/python: both python-cpp and python-net verified 200, no override
        # exists to resolve it). Previously resolve_backlink() never consulted this
        # -- the record was computed and sitting in platform_variant_authority.json,
        # but _lookup_platform()/alias-table iteration order silently picked
        # whichever variant happened to already be keyed in the target map,
        # exactly the "most obvious" judgment call the user asked to be made
        # deliberately, not by accident. An EXPLICIT_OVERRIDE decision (a
        # canonical_overrides entry already resolves the ambiguity) is not
        # blocked here -- only genuine, still-unresolved REVIEW_REQUIRED records are.
        if variant_authority:
            prefix = TARGET_HOST_TO_PREFIX.get(preferred_sd)
            if prefix:
                request_key = f"{prefix}/{family}/{platform}"
                variant_rec = variant_authority.get(request_key)
                if variant_rec and variant_rec.get("decision") == "REVIEW_REQUIRED":
                    alternatives = variant_rec.get("alternatives") or []
                    candidate_slugs = ", ".join(a.get("slug", "?") for a in alternatives)
                    return (
                        None,
                        ResolutionKind.AMBIGUOUS_PLATFORM_TARGETS,
                        preferred_sd,
                        f"{variant_rec.get('review_reason', 'multiple_verified_variants')}: "
                        f"candidates=[{candidate_slugs}]",
                    )

        # Check canonical override first (A2 P0 — only http_verified: true entries used)
        #
        # RC-OVERRIDE-SCOPE (found live 2026-08-26, backlink-governance-redesign
        # mission, TC13 continuation): every current entry's http_verified/
        # verification_url/verification_date evidence is a check against
        # products.aspose.com ONLY (confirmed by direct read of every entry in
        # platform_canonical_overrides.yaml) -- the file's own "Policy decision"
        # comment (2026-07-03, commit bb68a63a22) states this explicitly:
        # "Override scope: products.aspose.org source pages only (resolve_backlink
        # checks subdomain before applying overrides)." That claim was false: this
        # block previously applied every override unconditionally to ANY
        # source_subdomain, because _lookup_platform() only checks whether the
        # override's target platform slug HAPPENS to also exist (HTTP 200) on
        # whatever preferred_sd the current source resolves to -- not whether the
        # override's own evidence ever covered that target subdomain. Confirmed
        # live: barcode/python's override (verified only for
        # products.aspose.com/barcode/python-net/) was silently overriding
        # reference.aspose.org's resolution too, on 26 real pages, from their own
        # correct pre-existing https://reference.aspose.com/barcode/python-java/
        # links to the wrong .../barcode/python-net/ -- reference.aspose.com
        # genuinely publishes BOTH variants (a real binding-implementation
        # ambiguity products.aspose.com's simpler product-page structure doesn't
        # have), so the products.com-only evidence was never sufficient here.
        # Fixed: gate on an explicit source_subdomains allowlist, defaulting to
        # ["products.aspose.org"] (matching what every entry's evidence actually
        # supports) when the field is absent -- fail-closed for legacy entries.
        # pdf/go is the one entry with genuine cross-subdomain evidence in its own
        # notes (docs.aspose.com AND products.aspose.com both independently HTTP-
        # verified) and is the only entry given an explicit, wider
        # source_subdomains list in the data file for exactly that reason.
        if canonical_overrides:
            override_key = f"{family}/{platform}"
            override = canonical_overrides.get("overrides", {}).get(override_key)
            allowed_source_subdomains = override.get("source_subdomains") if override else None
            if allowed_source_subdomains is None:
                allowed_source_subdomains = ["products.aspose.org"]
            if (override and override.get("http_verified") is True
                    and source_subdomain in allowed_source_subdomains):
                override_platform = override.get("target_platform")
                if override_platform:
                    url = _lookup_platform(target_map, preferred_sd, family, override_platform)
                    if url:
                        return url, "platform", preferred_sd, None

        # Try platform URL on preferred subdomain
        url = _lookup_platform(target_map, preferred_sd, family, platform)
        if url:
            return url, "platform", preferred_sd, None

        # Fallback: family URL on preferred subdomain
        url = _lookup_family(target_map, preferred_sd, family)
        if url:
            return url, "family", preferred_sd, f"platform {family}/{platform} not found on {preferred_sd}"

        # No cross-section fallback to products.aspose.com for non-products sources.
        # Wrong-section links are worse than no link. Return BLOCKED.
        # Exception: products.aspose.org is self-referential; allow products self-fallback.
        if preferred_sd == "products.aspose.com":
            url = _lookup_platform(target_map, "products.aspose.com", family, platform)
            if url:
                return url, "platform", "products.aspose.com", "products self-fallback"
            url = _lookup_family(target_map, "products.aspose.com", family)
            if url:
                return url, "family", "products.aspose.com", "products self-fallback family"

        return None, None, None, f"no same-section target for {family}/{platform} on {preferred_sd}"

    else:
        # Family-only resolution
        url = _lookup_family(target_map, preferred_sd, family)
        if url:
            return url, "family", preferred_sd, None

        # No cross-section fallback for non-products sources.
        if preferred_sd == "products.aspose.com":
            url = _lookup_family(target_map, "products.aspose.com", family)
            if url:
                return url, "family", "products.aspose.com", "products self-fallback family"

        return None, None, None, f"no same-section family target for {family} on {preferred_sd}"


# ── Anchor suffix policy (§anchor-v3) ────────────────────────────────────────

_PRODUCTS_ASPOSE_RE = re.compile(r'https?://products\.aspose\.com/', re.IGNORECASE)
_DOCS_ASPOSE_RE     = re.compile(r'https?://docs\.aspose\.com/',     re.IGNORECASE)
_REF_ASPOSE_RE      = re.compile(r'https?://reference\.aspose\.com/', re.IGNORECASE)
_KB_ASPOSE_RE       = re.compile(r'https?://kb\.aspose\.com/',        re.IGNORECASE)
_BLOG_ASPOSE_RE     = re.compile(r'https?://blog\.aspose\.com/',      re.IGNORECASE)


def build_enterprise_anchor_suffix(target_url: str, target_type: str) -> str:
    """
    Return the Enterprise anchor suffix for target_url domain and type.

    Anchor text MUST be derived from the target domain (§anchor-v3):
      products.aspose.com family   -> "Enterprise Product Family"
      products.aspose.com platform -> "Enterprise Product"
      docs.aspose.com (any)        -> "Enterprise Documentation"
      reference.aspose.com (any)   -> "Enterprise API Reference"
      kb.aspose.com (any)          -> "Enterprise Knowledge Base"
      unknown domain               -> "Enterprise Product" (safe fallback)

    Args:
        target_url:  The resolved target URL.
        target_type: "family" or "platform" (only relevant for products.aspose.com).
    """
    if _PRODUCTS_ASPOSE_RE.search(target_url):
        return "Enterprise Product Family" if target_type == "family" else "Enterprise Product"
    if _DOCS_ASPOSE_RE.search(target_url):
        return "Enterprise Documentation"
    if _REF_ASPOSE_RE.search(target_url):
        return "Enterprise API Reference"
    if _KB_ASPOSE_RE.search(target_url):
        return "Enterprise Knowledge Base"
    if _BLOG_ASPOSE_RE.search(target_url):
        return "Enterprise Blog"
    return "Enterprise Product"  # unknown domain — safe fallback


def validate_anchor_suffix(anchor_text: str, target_url: str, target_type: str) -> list[str]:
    """
    Validate anchor_text uses the correct Enterprise suffix for target_url.
    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    is_docs = bool(_DOCS_ASPOSE_RE.search(target_url))
    is_ref  = bool(_REF_ASPOSE_RE.search(target_url))
    is_kb   = bool(_KB_ASPOSE_RE.search(target_url))
    is_prod = bool(_PRODUCTS_ASPOSE_RE.search(target_url))
    is_blog = bool(_BLOG_ASPOSE_RE.search(target_url))

    if is_blog:
        if "Enterprise Blog" not in anchor_text:
            errors.append(
                f"ANCHOR_DOMAIN_MISMATCH: blog URL {target_url!r} must use 'Enterprise Blog' suffix"
            )
        return errors

    if is_docs or is_ref or is_kb:
        if "Enterprise Product Family" in anchor_text:
            errors.append(
                f"ANCHOR_DOMAIN_MISMATCH: 'Enterprise Product Family' for non-products URL {target_url!r}"
            )
        if "Enterprise Product" in anchor_text and "Enterprise Product Family" not in anchor_text:
            errors.append(
                f"ANCHOR_DOMAIN_MISMATCH: 'Enterprise Product' for non-products URL {target_url!r}"
            )
    if is_prod and "Enterprise Documentation" in anchor_text:
        errors.append(
            f"ANCHOR_DOMAIN_MISMATCH: 'Enterprise Documentation' for products URL {target_url!r}"
        )
    if is_prod and "Enterprise API Reference" in anchor_text:
        errors.append(
            f"ANCHOR_DOMAIN_MISMATCH: 'Enterprise API Reference' for products URL {target_url!r}"
        )
    if is_prod and target_type == "family" and (
        "Enterprise Product" in anchor_text and "Enterprise Product Family" not in anchor_text
    ):
        errors.append(
            f"ANCHOR_TYPE_MISMATCH: family URL {target_url!r} has platform-level anchor text"
        )
    if is_prod and target_type == "platform" and "Enterprise Product Family" in anchor_text:
        errors.append(
            f"ANCHOR_TYPE_MISMATCH: platform URL {target_url!r} has family-level anchor text"
        )
    return errors


# ── Link extraction ───────────────────────────────────────────────────────────

def count_qualifying_com_links(body_text: str) -> tuple[int, list[str]]:
    """
    Count *.aspose.com/* links in body text.
    Strips code fences (```) and inline code before counting.
    Returns (count, [url_list]).
    """
    # Strip block fences
    stripped = CODE_FENCE_RE.sub("", body_text)
    # Strip inline code
    stripped = INLINE_CODE_RE.sub("", stripped)
    # Find all aspose.com URLs
    urls = COM_LINK_RE.findall(stripped)
    # Clean up (remove trailing punctuation sometimes captured)
    # Also exclude non-qualifying subdomains (e.g. forum.aspose.com)
    cleaned = []
    for u in urls:
        u = u.rstrip('.,;:)"\'')
        host = u.split("/")[2].lower() if u.count("/") >= 2 else ""
        if host in NON_QUALIFYING_COM_HOSTS:
            continue
        cleaned.append(u)
    return len(cleaned), cleaned


def detect_backlink_downgrade(before_body: str, after_body: str) -> str | None:
    """Pure, no I/O. TC13 (2026-08-26, backlink-governance-redesign): returns
    a reason string if after_body has ZERO qualifying aspose.com links while
    before_body had >=1 -- the exact shape of a real, live incident
    (commit ea05b9d8c8, "Task 14 upstream E2E proof run"): a full
    batch_reference.py --rebuild-all regeneration silently stripped 247
    reference.aspose.org/pdf/java pages' previously-correct backlinks
    because resolve_backlink() returned no target during that specific
    run, and nothing detected the drop before the page was written.

    Returns None for the normal "never had one"/"still has one" cases, and
    deliberately does NOT flag a WRONG_TARGET/WRONG_ANCHOR_TEXT-shaped
    regression (link count unchanged, content wrong) -- that is
    classify_compliance()'s job on the next audit pass, not this guard's;
    this guard exists specifically to block a full-regen writer from
    silently going from "has a link" to "has none", which classify_compliance()
    cannot prevent (it only ever runs after the fact, against whatever
    landed on disk).
    """
    before_count, _ = count_qualifying_com_links(before_body)
    if before_count == 0:
        return None
    after_count, _ = count_qualifying_com_links(after_body)
    if after_count == 0:
        return (f"BACKLINK_DOWNGRADE: page had {before_count} qualifying "
                f"aspose.com link(s) before regeneration, 0 after")
    return None


# TC2 (2026-08-21): markdown-link-aware extraction, giving (anchor_text, url)
# pairs instead of bare URLs -- needed to detect WRONG_ANCHOR_TEXT, which
# count_qualifying_com_links() structurally cannot see (it only ever
# extracted the URL half of a link, by design, for its original purpose).
# The anchor-text class deliberately excludes '[', ']', and newlines (not
# just ']') -- found live 2026-08-28 auditing reference.aspose.org/pdf/net
# pages: a `[^\]]+` class allows a stray, unpaired '[' elsewhere in the body
# (e.g. half-open interval notation like "the substring [fromInd, toInd)" in
# a method-table description) to be swallowed into the match, which then
# hunts across newlines/table rows for the next ']' -- landing on a real
# link's own closing bracket far downstream and extracting ~1400 chars of
# unrelated table prose as "anchor text" instead of the real, correct
# anchor. Real anchor text in this codebase's generated content is always a
# single line with no literal brackets, so excluding both bracket
# characters and '\n' from the class is a safe, non-lossy restriction.
MD_ASPOSE_COM_LINK_RE = re.compile(
    r'\[([^\[\]\n]+)\]\((https?://[a-z0-9.-]+\.aspose\.com/[^\s\)]*)\)',
    re.IGNORECASE,
)


def extract_qualifying_com_links(body_text: str) -> list[tuple[str, str]]:
    """Extract (anchor_text, url) pairs for qualifying *.aspose.com/* markdown
    links in body text. Same code-fence/inline-code stripping and
    NON_QUALIFYING_COM_HOSTS filtering as count_qualifying_com_links() --
    kept as a separate function rather than changing that one's return shape,
    since count_qualifying_com_links() has existing callers that expect a
    bare URL list and this is deliberately additive, not a replacement.
    """
    stripped = CODE_FENCE_RE.sub("", body_text)
    stripped = INLINE_CODE_RE.sub("", stripped)
    pairs = MD_ASPOSE_COM_LINK_RE.findall(stripped)
    cleaned: list[tuple[str, str]] = []
    for anchor_text, url in pairs:
        url = url.rstrip('.,;:)"\'')
        host = url.split("/")[2].lower() if url.count("/") >= 2 else ""
        if host in NON_QUALIFYING_COM_HOSTS:
            continue
        cleaned.append((anchor_text, url))
    return cleaned


# ── Compliance classification ─────────────────────────────────────────────────

def classify_compliance(
    existing_count: int,
    existing_urls: list[str],
    chosen_target_url: Optional[str],
    status_on_blocked: str = BLOCKED_TARGET,
    family: Optional[str] = None,
    platform: Optional[str] = None,
    *,
    chosen_target_type: Optional[str] = None,
    chosen_target_subdomain: Optional[str] = None,
    existing_links: Optional[list[tuple[str, str]]] = None,
    expected_anchor_text: Optional[str] = None,
) -> str:
    """
    Return compliance status.
    existing_count: qualifying aspose.com link count in page body
    existing_urls: the actual URLs found
    chosen_target_url: from resolve_backlink (None = BLOCKED_TARGET)
    family/platform: used to build the full acceptable fallback URL set per §Q.4
    chosen_target_type: "platform" or "family" from resolve_backlink (A2 P0)
    chosen_target_subdomain: e.g. "kb.aspose.com" from resolve_backlink (A2 P0)
    existing_links: (TC2, 2026-08-21) optional (anchor_text, url) pairs from
        extract_qualifying_com_links() -- when provided together with
        expected_anchor_text, enables WRONG_ANCHOR_TEXT detection. Omitting
        either keeps prior behavior exactly (backward compatible) -- every
        existing caller that only ever passed existing_urls is unaffected.
    expected_anchor_text: (TC2) the governed anchor text a compliant link on
        chosen_target_url must carry, e.g. from _expected_anchor_text() in
        backlink_backfill.py or the equivalent registry-driven computation
        for non-products subdomains.
    """
    if chosen_target_url is None:
        return status_on_blocked

    if existing_count == 0:
        return MISSING

    if existing_count > get_max_enterprise_links_per_page():
        return OVER_LIMIT

    # Build the set of all acceptable URLs (chosen + full fallback chain per §Q.4).
    # Any URL in the fallback chain is considered acceptable per plan §2.1.
    # All entries are normalized (stripped trailing slash, lowercased) for comparison.
    def _norm(u: str) -> str:
        return u.rstrip("/").lower()

    # A2 P0: Detect FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE before computing acceptable set.
    # If resolver found a platform-level target but existing URL is the family-level URL
    # on the same subdomain, the page is using a broader link than necessary.
    # TC2 (2026-08-21): this must only fire when the family URL is used INSTEAD OF the
    # platform target -- not when both are present at once, which is a DUPLICATE_LINK
    # case (confirmed live on 64 kb.aspose.org pages) and needs its own, more specific
    # status further down. Without this guard, this check fired unconditionally the
    # moment ANY existing URL matched the family URL, silently absorbing the duplicate
    # case and never letting the DUPLICATE_LINK detection below ever run.
    if chosen_target_type == "platform" and chosen_target_subdomain and family:
        family_url_on_sd = _norm(f"https://{chosen_target_subdomain}/{family}/")
        platform_target_also_present = _norm(chosen_target_url) in {_norm(u) for u in existing_urls}
        if not platform_target_also_present:
            for url in existing_urls:
                if _norm(url) == family_url_on_sd:
                    return FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE

    acceptable: set[str] = {_norm(chosen_target_url)}
    # TC2 (2026-08-21): the same-subdomain family URL is also an acceptable
    # single link (that's exactly what FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE
    # above alternatively classifies it as) -- adding it here lets the
    # DUPLICATE_LINK check below correctly count it as a second, redundant
    # acceptable match when the platform URL is ALSO present. Previously this
    # set only ever added products.aspose.com/docs.aspose.com/reference.aspose.com
    # family fallbacks unconditionally, never the actual resolution subdomain's
    # own family URL.
    if chosen_target_subdomain and family:
        acceptable.add(_norm(f"https://{chosen_target_subdomain}/{family}/"))

    # BL-DUP-CLASSIFIER-FIX (2026-08-24): snapshot the SAME-SUBDOMAIN-only
    # acceptable set (chosen target + its own family fallback) before the
    # cross-subdomain fallbacks below are added. DUPLICATE_LINK must only
    # ever compare candidates for the SAME governed backlink slot -- i.e.
    # two URLs that both live on chosen_target_subdomain. The cross-subdomain
    # entries added next (products/docs/reference.aspose.com family pages)
    # exist only so a single existing link on one of those hosts can still
    # count as an acceptable stand-in when chosen_target_subdomain's own link
    # is absent -- they are independent, legitimate references to different
    # aspose.com properties, not redundant copies of the governed link, and
    # must never feed duplicate-counting.
    same_subdomain_acceptable = set(acceptable)

    if family and chosen_target_subdomain != "blog.aspose.com":
        # Products family/platform are acceptable fallbacks for non-blog page types.
        # Blog pages must use blog.aspose.com — products.aspose.com is WRONG_TARGET for blog.
        acceptable.add(_norm(f"https://products.aspose.com/{family}/"))
        if platform:
            acceptable.add(_norm(f"https://products.aspose.com/{family}/{platform}/"))
        # Docs and reference family-level fallbacks
        acceptable.add(_norm(f"https://docs.aspose.com/{family}/"))
        acceptable.add(_norm(f"https://reference.aspose.com/{family}/"))

    # TC2 (2026-08-21), narrowed by BL-DUP-CLASSIFIER-FIX (2026-08-24):
    # DUPLICATE_LINK -- 2 distinct SAME-SUBDOMAIN acceptable URLs present at
    # once (e.g. both the family-level AND platform-level link, BOTH on
    # chosen_target_subdomain -- the exact defect confirmed live on 64
    # kb.aspose.org pages: a family "See Also" bullet never removed when a
    # platform-specific one was later appended). Scoped to
    # same_subdomain_acceptable rather than the full cross-subdomain
    # acceptable set -- reusing the full set here previously misclassified a
    # page with one correct same-subdomain link plus one unrelated,
    # legitimate cross-subdomain reference as a duplicate (confirmed live on
    # cells/go, pdf/net, words/net, and 13 kb.aspose.org pages overall).
    # Must run BEFORE the single-match COMPLIANT check below, since that
    # check would otherwise return COMPLIANT on the first acceptable URL it
    # finds and never notice a second, redundant one.
    distinct_acceptable_matches = {
        _norm(url) for url in existing_urls if _norm(url) in same_subdomain_acceptable
    }
    if len(distinct_acceptable_matches) > 1:
        return DUPLICATE_LINK

    # TC10 (2026-08-21): DUPLICATE_SUBDOMAIN -- 2+ distinct qualifying links
    # present (within budget, not already caught by DUPLICATE_LINK above),
    # but at least 2 of them share an aspose.com host. Must run before the
    # single-URL-match loop below, which would otherwise return COMPLIANT on
    # the first acceptable URL and never notice a same-host sibling.
    def _host(u: str) -> str:
        return u.split("://", 1)[-1].split("/", 1)[0].lower()

    distinct_existing = {_norm(u) for u in existing_urls}
    if len(distinct_existing) > 1:
        hosts = [_host(u) for u in distinct_existing]
        if len(set(hosts)) < len(hosts):
            return DUPLICATE_SUBDOMAIN

    # TC2 (2026-08-21), narrowed by BL-ANCHOR-SCOPE-FIX (2026-08-24):
    # WRONG_ANCHOR_TEXT -- correct URL, but the anchor text doesn't match the
    # governed registry wording. expected_anchor_text is computed by the
    # caller specifically FOR chosen_target_url, so it must only ever be
    # checked against THAT exact URL's own anchor text when present -- never
    # against a different, merely-acceptable cross-subdomain fallback URL.
    # Checked before the general acceptable-match loop below (not folded
    # into it) so that when chosen_target_url is genuinely present, its own
    # wording is always validated regardless of where it falls in
    # existing_urls -- an early return on some OTHER acceptable URL must not
    # skip checking the actual chosen link's anchor text. Confirmed live: a
    # docs.aspose.org page with both products.aspose.com/cells/ (correctly
    # worded "Enterprise Product Family") and the actual chosen
    # docs.aspose.com/cells/ target (correctly worded "Enterprise
    # Documentation") was misclassified WRONG_ANCHOR_TEXT because the old
    # single loop hit products.aspose.com/cells/ first and checked its
    # anchor text against docs.aspose.com's expected wording. Only checked
    # when both existing_links and expected_anchor_text are supplied
    # (keyword-only, opt-in -- omitting either preserves the exact prior
    # URL-only behavior for every existing caller).
    if (existing_links is not None and expected_anchor_text is not None
            and chosen_target_url is not None):
        chosen_norm = _norm(chosen_target_url)
        if any(_norm(u) == chosen_norm for u in existing_urls):
            matching_anchor_texts = {
                anchor for anchor, link_url in existing_links
                if _norm(link_url) == chosen_norm
            }
            if matching_anchor_texts and expected_anchor_text not in matching_anchor_texts:
                return WRONG_ANCHOR_TEXT

    # 1 or 2 links — COMPLIANT if any existing URL is in acceptable set
    for url in existing_urls:
        if _norm(url) in acceptable:
            return COMPLIANT

    # Parent-path coverage rule: if any existing URL is a URL-prefix of the chosen
    # target on the same host, the page is already covered at a higher level → COMPLIANT.
    # Example: https://kb.aspose.com/cells/python/ covers
    #          https://kb.aspose.com/cells/python/how-to-convert-csv-to-pdf/
    if chosen_target_url:
        target_norm_full = _norm(chosen_target_url)
        for url in existing_urls:
            url_norm = _norm(url)
            # Require non-trivial prefix (> 8 chars to exclude scheme+host-only matches)
            if len(url_norm) > 8 and target_norm_full.startswith(url_norm + "/"):
                return COMPLIANT

    # Links exist but none match acceptable fallback chain → WRONG_TARGET
    return WRONG_TARGET


# A7-03: KB anchor transition classifier
def classify_kb_anchor_status(
    existing_urls: list,
    kb_anchor_mode: str = LEGACY_COMPAT_MODE,
) -> str:
    """
    Classify KB anchor status based on existing URLs and the active kb_anchor_mode.

    Returns:
      CANONICAL_KB_POST_P0            — page already has kb.aspose.com link (correct)
      ACCEPTABLE_LEGACY_KB_PRE_P0     — page has docs.aspose.com link in LEGACY_COMPAT_MODE
      UPGRADE_CANDIDATE_NOT_YET_FIXED — page has docs.aspose.com link in CANONICAL_POST_P0_MODE
      MISSING                          — no qualifying KB or docs link found

    Pure function. No I/O.
    """
    for url in existing_urls:
        if "kb.aspose.com" in url:
            return CANONICAL_KB_POST_P0
    for url in existing_urls:
        if "docs.aspose.com" in url:
            if kb_anchor_mode == CANONICAL_POST_P0_MODE:
                return UPGRADE_CANDIDATE_NOT_YET_FIXED
            return ACCEPTABLE_LEGACY_KB_PRE_P0
    return MISSING


# ── A4: Platform variant authority ────────────────────────────────────────────

# A4 audit status constants
EXACT_PLATFORM_VERIFIED              = "EXACT_PLATFORM_VERIFIED"
VARIANT_CANONICAL_SELECTED           = "VARIANT_CANONICAL_SELECTED"
VARIANT_REVIEW_REQUIRED              = "VARIANT_REVIEW_REQUIRED"
VARIANT_BLOCKED_NO_POLICY            = "VARIANT_BLOCKED_NO_POLICY"
FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE = "FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE"
ANCESTOR_FALLBACK_AFTER_NO_VARIANT   = "ANCESTOR_FALLBACK_AFTER_NO_VARIANT"
VARIANT_CANDIDATES_NOT_IN_MAP        = "VARIANT_CANDIDATES_NOT_IN_MAP"
VARIANT_CANDIDATE_UNVERIFIED         = "VARIANT_CANDIDATE_UNVERIFIED"
SITEMAP_COVERAGE_GAP                 = "SITEMAP_COVERAGE_GAP"
MULTIPLE_VARIANTS_REQUIRES_REVIEW    = "MULTIPLE_VARIANTS_REQUIRES_REVIEW"


def load_platform_variant_registry(registry_path: Optional[Path] = None) -> dict:
    """
    Load data/backlinks/platform_variant_registry.yaml.
    Returns the parsed registry dict or empty dict if file missing.
    Pure function once file is loaded — no I/O side effects.
    """
    import yaml  # local import to avoid top-level dep when yaml absent
    if registry_path is None:
        registry_path = Path(__file__).resolve().parents[3] / "data" / "backlinks" / "platform_variant_registry.yaml"
    if not registry_path.exists():
        return {}
    return yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}


def load_variant_authority(authority_path: Optional[Path] = None) -> dict:
    """
    Load data/backlinks/workspace/platform_variant_authority.json.
    Returns the parsed authority dict keyed by request_key.
    Returns empty dict if file missing (graceful — system falls through to ancestor walk).
    """
    if authority_path is None:
        authority_path = (
            Path(__file__).resolve().parents[3]
            / "data" / "backlinks" / "workspace" / "platform_variant_authority.json"
        )
    if not authority_path.exists():
        return {}
    import json as _json
    data = _json.loads(authority_path.read_text(encoding="utf-8"))
    # Index by request_key for O(1) lookup
    if isinstance(data, list):
        return {rec["request_key"]: rec for rec in data if "request_key" in rec}
    if isinstance(data, dict) and "authority" in data:
        return {rec["request_key"]: rec for rec in data["authority"] if "request_key" in rec}
    return {}


def resolve_variant_target(
    request_key: str,
    variant_authority: dict,
    overrides: Optional[dict] = None,
) -> Optional[dict]:
    """
    Look up request_key in the variant authority.
    Returns the authority record if allowed_for_generation is True, else None.
    Pure function. No I/O. No HTTP.

    Args:
        request_key: e.g. "reference/words/python-net"
        variant_authority: loaded from load_variant_authority()
        overrides: canonical overrides dict (optional)
    Returns:
        dict with at least {"canonical_target_url": str, "decision": str} or None
    """
    if overrides:
        ovr = overrides.get(request_key)
        if ovr and ovr.get("http_verified") and ovr.get("canonical_target_url"):
            return {"canonical_target_url": ovr["canonical_target_url"],
                    "decision": "EXPLICIT_OVERRIDE", "allowed_for_generation": True}

    rec = variant_authority.get(request_key)
    if rec is None:
        return None
    if not rec.get("allowed_for_generation", False):
        return None
    return rec


# ── A5-Prep: Link Slot Registry ───────────────────────────────────────────────

from dataclasses import dataclass, field as dc_field
from typing import List

@dataclass
class SlotConfig:
    slot_id: str
    description: str
    insertion_section: str
    max_per_page: int
    eligible_page_types: List[str]
    eligible_target_types: List[str]
    fallback_slot: Optional[str]
    enabled: bool


_CANONICAL_OVERRIDES_CACHE: Optional[dict] = None
_CANONICAL_OVERRIDES_PATH: Optional[Path] = None


def load_canonical_overrides(repo_root: Optional[Path] = None) -> dict:
    """TC6 (2026-08-21): the single canonical loader for
    data/backlinks/platform_canonical_overrides.yaml's http_verified: true
    entries, returned as the raw {"overrides": {...}} dict resolve_backlink()
    expects for its canonical_overrides= parameter.

    Previously, callers of resolve_backlink() had to load and filter this
    file themselves -- backlink_backfill.py did (correctly); batch_reference.py
    and generate_product_backlink_copy.py never did at all, so every verified
    override was silently inert for those call sites regardless of the
    override table's own per-target-subdomain HTTP-200 verification logic
    inside resolve_backlink() -- confirmed as the same recurring
    call-site-omission pattern MT043 independently found and fixed once
    already, in readme_refresh_run.py. Caches after first load, path-aware
    (mirrors load_slot_registry()'s own pattern) so a different repo_root
    (e.g. in a test) is not served a stale cached value.
    """
    global _CANONICAL_OVERRIDES_CACHE, _CANONICAL_OVERRIDES_PATH
    root = Path(repo_root) if repo_root else _REPO_ROOT
    path = root / "data" / "backlinks" / "platform_canonical_overrides.yaml"
    if _CANONICAL_OVERRIDES_CACHE is not None and _CANONICAL_OVERRIDES_PATH == path:
        return _CANONICAL_OVERRIDES_CACHE
    try:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, OSError):
        raw = {}
    _CANONICAL_OVERRIDES_CACHE = raw
    _CANONICAL_OVERRIDES_PATH = path
    return raw


_SLOT_REGISTRY_CACHE: Optional[dict] = None
_SLOT_REGISTRY_PATH: Optional[Path] = None


def load_slot_registry(registry_path: Optional[Path] = None) -> dict:
    """
    Load data/backlinks/link_slot_registry.yaml.
    Returns dict keyed by slot_id -> SlotConfig.
    Raises FileNotFoundError if missing.
    Caches after first load.
    """
    global _SLOT_REGISTRY_CACHE, _SLOT_REGISTRY_PATH
    path = Path(registry_path) if registry_path else (_REPO_ROOT / "data" / "backlinks" / "link_slot_registry.yaml")
    if _SLOT_REGISTRY_CACHE is not None and _SLOT_REGISTRY_PATH == path:
        return _SLOT_REGISTRY_CACHE
    if not path.exists():
        raise FileNotFoundError(f"Slot registry not found: {path}")
    import yaml
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    slots: dict = {}
    for slot_id, cfg in raw.get("slots", {}).items():
        slots[slot_id] = SlotConfig(
            slot_id=slot_id,
            description=cfg.get("description", ""),
            insertion_section=cfg.get("insertion_section", "## See Also"),
            max_per_page=cfg.get("max_per_page", 1),
            eligible_page_types=cfg.get("eligible_page_types", []),
            eligible_target_types=cfg.get("eligible_target_types", []),
            fallback_slot=cfg.get("fallback_slot"),
            enabled=cfg.get("enabled", True),
        )
    _SLOT_REGISTRY_CACHE = slots
    _SLOT_REGISTRY_PATH = path
    return slots


_MAX_LINKS_CACHE: Optional[int] = None
_MAX_LINKS_CACHE_PATH: Optional[Path] = None
_MAX_LINKS_DEFAULT_FALLBACK = 2  # only used if the registry is missing/unreadable


def get_max_enterprise_links_per_page(registry_path: Optional[Path] = None) -> int:
    """TC9 (2026-08-21): the single source of truth for the max-qualifying-
    links-per-page cap, read from data/backlinks/link_slot_registry.yaml's
    global.max_enterprise_links_per_page field.

    Before this fix, this exact value was hardcoded independently in 3 places
    (backlink_backfill.py's MAX_QUALIFYING_LINKS, backlink_targets.py's
    classify_compliance() existing_count > 2 check, backlink_html_audit.py's
    own total > 2 check) that happened to agree (all "2") but had no wiring
    between them -- and this YAML file's own max_enterprise_links_per_page
    field, despite being schema-validated and documented as "enforced by"
    those exact 3 files, was never actually read by any of them. Cached with
    the same path-aware invalidation pattern as load_slot_registry() above,
    so passing a different registry_path (e.g. in a test) picks up the new
    value immediately rather than reusing a stale cache.
    """
    global _MAX_LINKS_CACHE, _MAX_LINKS_CACHE_PATH
    path = Path(registry_path) if registry_path else (_REPO_ROOT / "data" / "backlinks" / "link_slot_registry.yaml")
    if _MAX_LINKS_CACHE is not None and _MAX_LINKS_CACHE_PATH == path:
        return _MAX_LINKS_CACHE
    try:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        value = raw.get("global", {}).get("max_enterprise_links_per_page")
        if not isinstance(value, int) or value < 1:
            value = _MAX_LINKS_DEFAULT_FALLBACK
    except (FileNotFoundError, OSError):
        value = _MAX_LINKS_DEFAULT_FALLBACK
    _MAX_LINKS_CACHE = value
    _MAX_LINKS_CACHE_PATH = path
    return value


def get_slot_for_page_type(page_type_str: str, registry: Optional[dict] = None) -> Optional[SlotConfig]:
    """
    Return the most specific enabled SlotConfig for the given PageType string.
    Returns None for BLOCKED/SKIP page types.
    """
    _BLOCKED_TYPES = {
        "BLOG_ARCHIVE", "BLOG_UTILITY", "SUBDOMAIN_ROOT",
        "LOCALE_FILE", "LOCALE_DIR", "UNKNOWN_PATTERN",
        "PRODUCTS_ROOT",
    }
    if page_type_str in _BLOCKED_TYPES:
        return None
    if registry is None:
        try:
            registry = load_slot_registry()
        except FileNotFoundError:
            return None
    for slot_id in ("enterprise_deep_primary", "enterprise_platform_landing", "enterprise_family_landing"):
        slot = registry.get(slot_id)
        if slot is None or not slot.enabled:
            continue
        if page_type_str in slot.eligible_page_types:
            return slot
    return None


def slot_fallback_chain(slot_id: str, registry: dict) -> List[str]:
    """Return ordered chain of slot IDs from slot_id following fallback_slot links."""
    chain = []
    current = slot_id
    visited = set()
    while current and current not in visited:
        chain.append(current)
        visited.add(current)
        slot = registry.get(current)
        current = slot.fallback_slot if slot else None
    return chain


# ── A6: Anchor Text Registry ──────────────────────────────────────────────────

import hashlib as _hashlib


class AnchorPolicyError(Exception):
    """Raised when render_anchor_text() is called for a SKIP/BLOCKED page type or bridge slug."""


# Audit status constants (A6)
AUTHORITY_ANCHOR_STALE     = "AUTHORITY_ANCHOR_STALE"
ANCHOR_CONFIG_HASH_MISMATCH = "ANCHOR_CONFIG_HASH_MISMATCH"


# SKIP/BLOCKED PageTypes — render_anchor_text() raises AnchorPolicyError for these
_ANCHOR_SKIP_TYPES = frozenset({
    "BLOG_ARCHIVE", "BLOG_UTILITY", "SUBDOMAIN_ROOT", "LOCALE_FILE",
    "LOCALE_DIR", "UNKNOWN_PATTERN", "PRODUCTS_ROOT",
})
_ANCHOR_DEFERRED_TYPES = frozenset({"DOCS_ARTICLE", "BLOG_POST"})

_ANCHOR_REGISTRY_CACHE: Optional[dict] = None
_ANCHOR_REGISTRY_PATH_CACHE: Optional[Path] = None


def load_anchor_registry(registry_path: Optional[Path] = None) -> dict:
    """
    Load data/backlinks/anchor_text_registry.yaml.
    Raises FileNotFoundError if missing (not silently graceful — same as load_target_map).
    Caches after first load.
    """
    global _ANCHOR_REGISTRY_CACHE, _ANCHOR_REGISTRY_PATH_CACHE
    path = Path(registry_path) if registry_path else (
        _REPO_ROOT / "data" / "backlinks" / "anchor_text_registry.yaml"
    )
    if _ANCHOR_REGISTRY_CACHE is not None and _ANCHOR_REGISTRY_PATH_CACHE == path:
        return _ANCHOR_REGISTRY_CACHE
    if not path.exists():
        raise FileNotFoundError(f"Anchor text registry not found: {path}")
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _ANCHOR_REGISTRY_CACHE = data
    _ANCHOR_REGISTRY_PATH_CACHE = path
    return data


def compute_anchor_config_hash(registry_path: Optional[Path] = None) -> str:
    """
    Compute deterministic semantic hash of anchor_text_registry.yaml.

    Algorithm (A7-06 canonical JSON):
      1. Parse YAML with yaml.safe_load()
      2. Remove 'config_hash' key if present
      3. json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
      4. SHA-256 of UTF-8 bytes
      5. Return "sha256:" + full hexdigest

    Comments and whitespace do NOT affect the hash.
    Key ordering is stable (sort_keys=True).
    """
    import json as _json
    import yaml
    path = Path(registry_path) if registry_path else (
        _REPO_ROOT / "data" / "backlinks" / "anchor_text_registry.yaml"
    )
    if not path.exists():
        raise FileNotFoundError(f"Anchor text registry not found for hashing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.pop("config_hash", None)
    canonical = _json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = _hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return "sha256:" + digest


def render_anchor_text(
    template_id: str,
    family: str,
    platform: Optional[str],
    target_url: str,
    registry: dict,
    families_map: dict,
    platforms_map: dict,
) -> str:
    """
    Render anchor link text from registry template.

    INVARIANT: platform MUST be canonical key (e.g., "python"), NEVER bridge slug (e.g., "python-net").
    Bridge slugs are rejected with AnchorPolicyError (A7-12).

    Raises:
        AnchorPolicyError: if template_id not found, bridge slug passed, or SKIP/BLOCKED page type
    """
    import json as _json
    # Check bridge slugs
    policy = registry.get("display_platform_policy", {})
    known_bridges = set(policy.get("known_bridge_slugs", []))
    if platform in known_bridges:
        raise AnchorPolicyError(
            f"Bridge slug {platform!r} passed as platform to render_anchor_text(). "
            f"Pass canonical key instead (e.g., 'python' for 'python-net')."
        )

    templates = registry.get("templates", {})
    if template_id not in templates:
        raise AnchorPolicyError(f"Unknown template_id: {template_id!r}")

    template = templates[template_id]
    fam = families_map.get(family, f"Aspose.{family.title()}")
    text = template["anchor_text"]
    text = text.replace("{fam}", fam)

    if platform:
        plat_display = platforms_map.get(platform, platform.title())
        text = text.replace("{plat}", plat_display)

    return text


def select_anchor_template_id(
    target_url: str,
    target_type: str,
    source_subdomain: Optional[str] = None,
) -> str:
    """
    Select the appropriate anchor template_id from target_url, target_type, and optional source_subdomain.

    Selection order:
      1. (source_subdomain, target_subdomain, target_type) match
      2. (target_subdomain, target_type) match
      3. safe_fallback template_id
    """
    # Determine target subdomain from URL
    target_sd = None
    for sd in ("reference.aspose.com", "docs.aspose.com", "kb.aspose.com",
               "products.aspose.com", "blog.aspose.com"):
        if sd in target_url:
            target_sd = sd
            break

    # Blog source with blog.aspose.com target uses blog-family/platform templates (D1 fix)
    if source_subdomain == "blog.aspose.org" and target_sd == "blog.aspose.com":
        return "blog-family" if target_type == "family" else "blog-platform"

    # Blog source with products target (legacy, deprecated — used only while old links exist)
    if source_subdomain == "blog.aspose.org" and target_sd == "products.aspose.com":
        return "blog-products-family" if target_type == "family" else "blog-products-platform"

    if target_sd == "docs.aspose.com":
        return "docs-family" if target_type == "family" else "docs-platform"
    elif target_sd == "kb.aspose.com":
        return "kb-family" if target_type == "family" else "kb-platform"
    elif target_sd == "reference.aspose.com":
        return "reference-family" if target_type == "family" else "reference-platform"
    elif target_sd == "products.aspose.com":
        return "products-family" if target_type == "family" else "products-platform"
    elif target_sd == "blog.aspose.com":
        return "blog-family" if target_type == "family" else "blog-platform"

    # Unknown domain — safe fallback
    return "products-platform"
