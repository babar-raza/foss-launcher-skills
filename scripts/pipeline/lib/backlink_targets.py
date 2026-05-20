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
    "python": "python", "py": "python", "python3": "python", "python-net": "python", "python-java": "python",
    "java": "java", "java8": "java", "java11": "java", "java-android": "java",
    "cpp": "cpp", "c-plus-plus": "cpp", "cplusplus": "cpp", "c++": "cpp",
    "nodejs": "nodejs", "node": "nodejs", "node-js": "nodejs", "javascript": "nodejs", "js": "nodejs",
    "android": "android", "android-java": "android",
    "cloud": "cloud", "rest-api": "cloud", "api": "cloud", "saas": "cloud",
    "ruby": "ruby", "ruby-net": "ruby",
    "go": "go", "golang": "go",
    "typescript": "typescript",
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
    "kb.aspose.org":        "docs.aspose.com",
    "reference.aspose.org": "reference.aspose.com",
    "products.aspose.org":  "products.aspose.com",
    "blog.aspose.org":      "products.aspose.com",
}




def configure(*, repo_root: "Path | str | None" = None,
              subdomain_roots: "dict[str, str] | None" = None) -> None:
    """Override module-level path constants for testing or alternate layouts."""
    global _REPO_ROOT, SUBDOMAIN_ROOTS
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
    if subdomain_roots is not None:
        SUBDOMAIN_ROOTS.clear()
        SUBDOMAIN_ROOTS.update(subdomain_roots)

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
    return None


def _lookup_family(target_map: dict, subdomain: str, family: str) -> Optional[str]:
    """Look up family-level URL in target map. Returns URL if http_status==200, else None."""
    entry = target_map.get("targets", {}).get(subdomain, {}).get("families", {}).get(family)
    if entry and entry.get("http_status") == 200:
        return entry.get("url")
    return None


def resolve_backlink(
    family: Optional[str],
    platform: Optional[str],
    source_subdomain: str,
    target_map: dict,
    *,
    exact_deep_match_enabled: bool = False,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve the best backlink target URL per §Q.4 default fallback matrix.
    Returns (chosen_url, chosen_type, chosen_subdomain, fallback_reason).
    chosen_url is None on BLOCKED_TARGET.

    exact_deep_match_enabled: If True, attempt exact deep URL lookup (future enhancement).
    Default is False per §J.1.
    """
    if not family:
        return None, None, None, "no family detected"

    preferred_sd = PREFERRED_TARGET_SUBDOMAIN.get(source_subdomain, "products.aspose.com")

    if platform:
        # Try platform URL on preferred subdomain
        url = _lookup_platform(target_map, preferred_sd, family, platform)
        if url:
            return url, "platform", preferred_sd, None

        # Fallback: family URL on preferred subdomain
        url = _lookup_family(target_map, preferred_sd, family)
        if url:
            return url, "family", preferred_sd, f"platform {family}/{platform} not found on {preferred_sd}"

        # Fallback: platform URL on products.aspose.com
        if preferred_sd != "products.aspose.com":
            url = _lookup_platform(target_map, "products.aspose.com", family, platform)
            if url:
                return url, "platform", "products.aspose.com", f"{preferred_sd} missing; fell back to products"

        # Fallback: family URL on products.aspose.com
        url = _lookup_family(target_map, "products.aspose.com", family)
        if url:
            return url, "family", "products.aspose.com", f"platform and preferred subdomain unavailable; family fallback on products"

        return None, None, None, f"no safe target after full fallback chain for {family}/{platform}"

    else:
        # Family-only resolution
        url = _lookup_family(target_map, preferred_sd, family)
        if url:
            return url, "family", preferred_sd, None

        if preferred_sd != "products.aspose.com":
            url = _lookup_family(target_map, "products.aspose.com", family)
            if url:
                return url, "family", "products.aspose.com", f"preferred subdomain missing family; fell back to products"

        return None, None, None, f"family target not found for {family} — target-map defect"


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
    cleaned = []
    for u in urls:
        u = u.rstrip('.,;:)"\'')
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
) -> str:
    """
    Return compliance status.
    existing_count: qualifying aspose.com link count in page body
    existing_urls: the actual URLs found
    chosen_target_url: from resolve_backlink (None = BLOCKED_TARGET)
    family/platform: used to build the full acceptable fallback URL set per §Q.4
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

    acceptable: set[str] = {_norm(chosen_target_url)}
    if family:
        # Products family/platform are always the final-resort fallbacks for any page type
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
