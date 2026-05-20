# Adapted from aspose.org
"""blog_slug_policy.py — Shared folder slug policy for blog.aspose.org.

Provides classification, validation, repair proposal, and URL derivation
for blog folder slugs. All other slug-related scripts import from this module.

Blog slug = the directory name immediately above index.md:
    content/blog.aspose.org/{family}/{platform}/{folder-slug}/index.md
    canonical URL: /{family}/{platform}/{folder-slug}/

No frontmatter slug: field is required or added. Hugo derives the URL entirely
from the folder path.
"""
from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Slug normalization
# ---------------------------------------------------------------------------

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "from", "by", "as", "is", "are", "be", "been", "being",
    "was", "were", "will", "have", "has", "had", "do", "does", "did",
    "its", "this", "that", "these", "those", "how", "what", "which",
    "foss", "aspose",
})


def normalize_folder_slug(text: str) -> str:
    """Normalize arbitrary text to a URL-safe folder slug (lowercase, hyphens only).

    Example: "Core Cell Operations in Java!" → "core-cell-operations-in-java"
    """
    lowered = text.lower()
    slugified = _NORMALIZE_RE.sub("-", lowered).strip("-")
    # Collapse repeated hyphens
    return re.sub(r"-{2,}", "-", slugified)


# ---------------------------------------------------------------------------
# Generic / bad slug detection
# ---------------------------------------------------------------------------

# Words that make a slug generic when used as the primary noun before "-in-{platform}"
_GENERIC_PREFIXES = frozenset({
    "core", "common", "util", "utils", "helper", "helpers", "base",
    "general", "main", "default", "overview", "basic", "features",
    "data", "model", "models", "internal", "shared",
})

# Known fallback slug patterns (used when no real slug could be derived)
_FALLBACK_PATTERNS = re.compile(
    r"^(generated-post(-\d+)?|untitled(-\d+)?|overview|basic|features)$"
)

# Pattern: {word}-in-{platform}
_GENERIC_IN_PLATFORM_RE = re.compile(r"^([a-z][a-z0-9]*)-in-([a-z]+)$")


def is_generic_folder_slug(folder_slug: str, family: str, platform: str) -> bool:
    """Return True if the slug is generic — does not identify the product.

    Generic means:
    - Matches ^{generic_word}-in-{platform}$ where the prefix is a generic word
    - Matches known fallback patterns
    - Is only the platform name
    - Is only the family name
    """
    if not folder_slug:
        return True
    slug = folder_slug.lower()

    # Pure platform or family name
    if slug in {platform.lower(), family.lower()}:
        return True

    # Known fallback patterns
    if _FALLBACK_PATTERNS.match(slug):
        return True

    # {generic_word}-in-{platform}
    m = _GENERIC_IN_PLATFORM_RE.match(slug)
    if m:
        prefix = m.group(1)
        if prefix in _GENERIC_PREFIXES:
            return True

    return False


# ---------------------------------------------------------------------------
# Slug quality classification
# ---------------------------------------------------------------------------

# Classification constants
OK = "OK"
WEAK = "WEAK"
BAD_GENERIC = "BAD_GENERIC"
BAD_FALLBACK = "BAD_FALLBACK"
BAD_NO_PLATFORM = "BAD_NO_PLATFORM"
BAD_TOO_SHORT = "BAD_TOO_SHORT"
MIGRATION_READY = "MIGRATION_READY"
NEEDS_REVIEW = "NEEDS_REVIEW"
BLOCKED_BY_GOVERNANCE = "BLOCKED_BY_GOVERNANCE"


def classify_folder_slug_quality(
    folder_slug: str,
    title: str,
    family: str,
    platform: str,
    product_name: str = "",
    auto_updatable: bool = True,
    content_origin: str = "skill-generated",
) -> str:
    """Classify a folder slug's SEO and identity quality.

    Returns one of: OK, WEAK, BAD_GENERIC, BAD_FALLBACK, BAD_NO_PLATFORM,
    BAD_TOO_SHORT, MIGRATION_READY, NEEDS_REVIEW, BLOCKED_BY_GOVERNANCE.

    Only auto_updatable skill-generated content with a BAD classification
    becomes MIGRATION_READY. Human-authored or protected content becomes
    BLOCKED_BY_GOVERNANCE if BAD.
    """
    slug = folder_slug.lower()
    fam = family.lower()
    plat = platform.lower()

    # Governance block check
    is_blocked = (not auto_updatable) or (content_origin == "manual-remediation")

    # Too short
    if len(slug) < 8:
        classification = BAD_TOO_SHORT
        return BLOCKED_BY_GOVERNANCE if is_blocked else MIGRATION_READY

    # Known fallback patterns
    if _FALLBACK_PATTERNS.match(slug):
        classification = BAD_FALLBACK
        return BLOCKED_BY_GOVERNANCE if is_blocked else MIGRATION_READY

    # Generic {word}-in-{platform}
    if is_generic_folder_slug(slug, fam, plat):
        classification = BAD_GENERIC
        return BLOCKED_BY_GOVERNANCE if is_blocked else MIGRATION_READY

    # No platform identity
    if plat not in slug and plat != "python":
        # Python products sometimes use generic slugs without "python" in name
        # Check if family is present at least
        if fam not in slug and (product_name and product_name.lower() not in slug):
            return NEEDS_REVIEW
        # Has family but no platform
        return BAD_NO_PLATFORM

    # Has platform: check for family/product identity
    has_family = fam in slug
    has_product = bool(product_name) and product_name.lower().replace(" ", "-") in slug

    if has_family or has_product:
        return OK

    # Platform present but no family/product identity
    return WEAK


# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------

def validate_folder_slug(
    folder_slug: str,
    title: str,
    family: str,
    platform: str,
    role: str = "",
) -> list[str]:
    """Validate that a slug passes all policy rules.

    Returns a list of violation strings (empty = passes all rules).
    """
    violations = []
    slug = folder_slug.lower()
    fam = family.lower()
    plat = platform.lower()

    if len(slug) < 8:
        violations.append(f"Slug '{folder_slug}' is too short (< 8 chars)")

    if _FALLBACK_PATTERNS.match(slug):
        violations.append(f"Slug '{folder_slug}' matches a known fallback pattern")

    if is_generic_folder_slug(slug, fam, plat):
        violations.append(
            f"Slug '{folder_slug}' is generic — does not identify product/family"
        )

    if len(slug) > 80:
        violations.append(f"Slug '{folder_slug}' exceeds 80 characters")

    # Must contain only lowercase letters, digits, hyphens
    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", slug):
        violations.append(
            f"Slug '{folder_slug}' contains invalid characters (only a-z, 0-9, hyphen allowed)"
        )

    return violations


# ---------------------------------------------------------------------------
# Repair slug proposal
# ---------------------------------------------------------------------------

def propose_folder_slug_repair(
    old_slug: str,
    title: str,
    family: str,
    platform: str,
    product_name: str = "",
    role: str = "",
) -> str:
    """Propose the best repair slug derived from the post title.

    Algorithm:
    1. Normalize title to slug form
    2. Remove stopwords (keep family/product/platform words)
    3. Ensure family or product identity appears
    4. Ensure platform appears
    5. Truncate to 60 chars at word boundary
    """
    # Step 1: normalize title
    raw = normalize_folder_slug(title)
    parts = [p for p in raw.split("-") if p]

    # Step 2: remove stopwords, but always keep family/product/platform tokens
    fam = family.lower()
    plat = platform.lower()
    kept = []
    for p in parts:
        if p in _STOPWORDS and p not in {fam, plat}:
            # Keep if it's a unique product token
            if product_name and p in product_name.lower().replace(" ", "-"):
                kept.append(p)
            # else skip stopword
        else:
            kept.append(p)

    # Step 3-4: check for family and platform presence
    slug_str = "-".join(kept)

    # Ensure family is in slug
    if fam not in slug_str:
        kept = [fam] + kept

    # Ensure platform is in slug
    if plat not in slug_str:
        kept = kept + [plat]

    slug_str = "-".join(kept)

    # Step 5: truncate to 60 chars at word boundary
    if len(slug_str) > 60:
        parts_60 = []
        length = 0
        for p in slug_str.split("-"):
            if length + len(p) + (1 if parts_60 else 0) > 60:
                break
            parts_60.append(p)
            length += len(p) + (1 if len(parts_60) > 1 else 0)
        slug_str = "-".join(parts_60)

    # Final cleanup
    slug_str = re.sub(r"-{2,}", "-", slug_str).strip("-")
    return slug_str


# ---------------------------------------------------------------------------
# URL / path derivation
# ---------------------------------------------------------------------------

def build_blog_url_from_index_path(index_md_path: "str | Path") -> str:
    """Build the canonical blog URL from an index.md path.

    content/blog.aspose.org/cells/java/core-in-java/index.md
    → /cells/java/core-in-java/
    """
    p = Path(index_md_path)
    # Walk up to find blog.aspose.org anchor
    parts = list(p.parts)
    try:
        anchor_idx = next(
            i for i, part in enumerate(parts) if part == "blog.aspose.org"
        )
    except StopIteration:
        # Fallback: use relative structure
        # {family}/{platform}/{slug}/index.md
        rel_parts = parts[:-1]  # drop index.md
        return "/" + "/".join(rel_parts[-3:]) + "/"

    # Parts after blog.aspose.org, minus index.md
    url_parts = parts[anchor_idx + 1: -1]  # exclude index.md
    return "/" + "/".join(url_parts) + "/"


def build_index_path_from_blog_url(url: str, content_root: Path) -> Path:
    """Build the index.md path from a canonical blog URL.

    url: /cells/java/core-in-java/
    → content_root/blog.aspose.org/cells/java/core-in-java/index.md
    """
    clean = url.strip("/")
    return content_root / "blog.aspose.org" / clean / "index.md"
