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
    "rust": "rust", "rust-cpp": "rust",
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

# A5-L6: Source-type policy statuses
STRUCTURAL_PAGE_SKIP = "STRUCTURAL_PAGE_SKIP"   # auto_updatable: false, no slot
DEFERRED_NO_TARGETS  = "DEFERRED_NO_TARGETS"    # DOCS_ARTICLE/BLOG_POST: no deep targets available

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
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve the best backlink target URL per §Q.4 default fallback matrix.
    Returns (chosen_url, chosen_type, chosen_subdomain, fallback_reason).
    chosen_url is None on BLOCKED_TARGET.

    exact_deep_match_enabled: If True, consult deep backlink authority (Layer 3).
    Default is False per §J.1 — v1 behavior is byte-identical when False.

    canonical_overrides: Optional dict loaded from platform_canonical_overrides.yaml.
    Only entries with http_verified: true are applied. (A2 P0)

    authority: Layer 3 approved backlink authority dict (loaded from backlink_authority.json).
    source_file: Repo-relative path of the source content file for authority lookup.
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
        # Check canonical override first (A2 P0 — only http_verified: true entries used)
        if canonical_overrides:
            override_key = f"{family}/{platform}"
            override = canonical_overrides.get("overrides", {}).get(override_key)
            if override and override.get("http_verified") is True:
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
) -> str:
    """
    Return compliance status.
    existing_count: qualifying aspose.com link count in page body
    existing_urls: the actual URLs found
    chosen_target_url: from resolve_backlink (None = BLOCKED_TARGET)
    family/platform: used to build the full acceptable fallback URL set per §Q.4
    chosen_target_type: "platform" or "family" from resolve_backlink (A2 P0)
    chosen_target_subdomain: e.g. "kb.aspose.com" from resolve_backlink (A2 P0)
    """
    if chosen_target_url is None:
        return status_on_blocked

    if existing_count == 0:
        return MISSING

    if existing_count > 2:
        return OVER_LIMIT

    # Build the set of all acceptable URLs (chosen + full fallback chain per §Q.4).
    # Any URL in the fallback chain is considered acceptable per plan §2.1.
    # All entries are normalized (stripped trailing slash, lowercased) for comparison.
    def _norm(u: str) -> str:
        return u.rstrip("/").lower()

    # A2 P0: Detect FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE before computing acceptable set.
    # If resolver found a platform-level target but existing URL is the family-level URL
    # on the same subdomain, the page is using a broader link than necessary.
    if chosen_target_type == "platform" and chosen_target_subdomain and family:
        family_url_on_sd = _norm(f"https://{chosen_target_subdomain}/{family}/")
        for url in existing_urls:
            if _norm(url) == family_url_on_sd:
                return FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE

    acceptable: set[str] = {_norm(chosen_target_url)}
    if family and chosen_target_subdomain != "blog.aspose.com":
        # Products family/platform are acceptable fallbacks for non-blog page types.
        # Blog pages must use blog.aspose.com — products.aspose.com is WRONG_TARGET for blog.
        acceptable.add(_norm(f"https://products.aspose.com/{family}/"))
        if platform:
            acceptable.add(_norm(f"https://products.aspose.com/{family}/{platform}/"))
        # Docs and reference family-level fallbacks
        acceptable.add(_norm(f"https://docs.aspose.com/{family}/"))
        acceptable.add(_norm(f"https://reference.aspose.com/{family}/"))

    # 1 or 2 links — COMPLIANT if any existing URL is in acceptable set
    for url in existing_urls:
        if _norm(url) in acceptable:
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
