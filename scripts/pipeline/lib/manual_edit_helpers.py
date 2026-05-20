# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
"""
helpers for S-73 manual-edit skill — section detection, scope validation, and rule loading.

These functions encode the deterministic, testable logic from the manual-edit skill spec.
The skill file (skills/manual-edit.md) references these rules; this module makes them
explicit and independently testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Ordered by prefix length (longest-first avoids accidental partial matches).
_SECTION_PREFIXES: list[tuple[str, str]] = [
    ("content/blog.aspose.org/", "blog"),
    ("content/docs.aspose.org/", "docs"),
    ("content/kb.aspose.org/", "kb"),
    ("content/products.aspose.org/", "products"),
    ("content/reference.aspose.org/", "reference"),
]


def detect_section(relative_path: str) -> Optional[str]:
    """Return the section name for a content file path, or None if unknown.

    Args:
        relative_path: Path relative to repo root, using forward slashes.

    Returns:
        One of "blog", "docs", "kb", "products", "reference", or None.
    """
    normalised = relative_path.replace("\\", "/").lstrip("/")
    for prefix, section in _SECTION_PREFIXES:
        if normalised.startswith(prefix):
            return section
    return None


def extract_family_platform(relative_path: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (family, platform) from a content file path.

    Path structure:
      blog:      content/blog.aspose.org/{family}/{platform}/...
      docs/kb:   content/{site}/en/{family}/{platform}/...
      products:  content/products.aspose.org/en/{family}/_index.md           (family page, layout: family)
                 content/products.aspose.org/en/{family}/{platform}/_index.md  (platform page, layout: plugin)
      reference: content/reference.aspose.org/en/{family}/{platform}/...

    Returns (family, platform) or (None, None) if extraction fails.
    """
    normalised = relative_path.replace("\\", "/").lstrip("/")
    section = detect_section(normalised)
    if section is None:
        return None, None

    parts = Path(normalised).parts  # ('content', 'docs.aspose.org', 'en', '{family}', ...)

    if section == "blog":
        # content/blog.aspose.org/{family}/{platform}/...
        if len(parts) >= 4:
            return parts[2], parts[3]
        return None, None

    if section == "products":
        # content/products.aspose.org/en/{family}/_index.md             (5 parts) → family page
        # content/products.aspose.org/en/{family}/{platform}/_index.md  (6 parts) → platform page
        if len(parts) >= 6:
            return parts[3], parts[4]  # family, platform
        if len(parts) >= 4:
            return parts[3], None  # family page only
        return None, None

    # docs, kb, reference: content/{site}/en/{family}/{platform}/...
    if len(parts) >= 5:
        return parts[3], parts[4]
    return None, None


# ---------------------------------------------------------------------------
# Scope validation
# ---------------------------------------------------------------------------

VALID_SCOPES = frozenset({
    "frontmatter-only",
    "body-wording",
    "code-snippet",
    "section-replacement",
    "full-remediation",
})

# Scopes that require --section argument
SCOPES_REQUIRING_SECTION = frozenset({"code-snippet", "section-replacement"})

# Scopes that require --evidence argument
SCOPES_REQUIRING_EVIDENCE = frozenset({"full-remediation"})

# Frontmatter fields that are system-managed and must not be touched by operator intent
SYSTEM_MANAGED_FRONTMATTER_FIELDS = frozenset({
    "evidence",
    "grade",
    "graded_at",
    "graded_model_sha",
    "graded_evaluators",
    "graded_logic_version",
    "provenance",
})


@dataclass
class ScopeValidationResult:
    valid: bool
    reason: str = ""


def validate_scope(
    edit_scope: str,
    target_section: Optional[str],
    evidence_justification: Optional[str],
) -> ScopeValidationResult:
    """Validate scope arguments against skill contract rules.

    Returns ScopeValidationResult with valid=True if all rules pass,
    or valid=False with a reason string describing the first violation.
    """
    if edit_scope not in VALID_SCOPES:
        return ScopeValidationResult(
            valid=False,
            reason=(
                f"Unknown scope '{edit_scope}' — valid scopes: "
                + ", ".join(sorted(VALID_SCOPES))
            ),
        )

    if edit_scope in SCOPES_REQUIRING_SECTION and not target_section:
        return ScopeValidationResult(
            valid=False,
            reason=f"Scope '{edit_scope}' requires --section to identify the target heading",
        )

    if edit_scope in SCOPES_REQUIRING_EVIDENCE and not evidence_justification:
        return ScopeValidationResult(
            valid=False,
            reason="Scope 'full-remediation' requires --evidence to justify the change",
        )

    return ScopeValidationResult(valid=True)


def intent_touches_system_field(edit_intent: str) -> Optional[str]:
    """Return the system-managed field name if intent would touch it, else None.

    Returns the longest matching field name to avoid 'grade' shadowing 'graded_at'.
    """
    intent_lower = edit_intent.lower()
    # Sort by length descending so longer names (e.g. graded_at) are checked before
    # their prefixes (e.g. grade).
    for field_name in sorted(SYSTEM_MANAGED_FRONTMATTER_FIELDS, key=len, reverse=True):
        if field_name in intent_lower:
            return field_name
    return None


# ---------------------------------------------------------------------------
# Section rules table
# ---------------------------------------------------------------------------

@dataclass
class SectionRules:
    section: str
    evidence_required: bool          # claims + apis must be non-empty
    author_field_required: bool      # must be exactly "Aspose"
    type_field_value: Optional[str]  # expected value of 'type' field (or None if not enforced)
    code_examples_policy: str        # "recommended" | "discouraged" | "in_steps"
    grading_active: bool
    draft_field_required: bool
    index_shortcode: Optional[str]   # shortcode required on index pages (or None)
    forbidden_frontmatter_fields: frozenset = field(
        default_factory=lambda: SYSTEM_MANAGED_FRONTMATTER_FIELDS
    )


_SECTION_RULES: dict[str, SectionRules] = {
    "blog": SectionRules(
        section="blog",
        evidence_required=True,
        author_field_required=True,
        type_field_value=None,
        code_examples_policy="recommended",
        grading_active=True,
        draft_field_required=True,
        index_shortcode=None,
    ),
    "docs": SectionRules(
        section="docs",
        evidence_required=True,   # for content pages; index pages may be empty
        author_field_required=False,
        type_field_value="docs",
        code_examples_policy="recommended",
        grading_active=True,
        draft_field_required=False,
        index_shortcode="{{< sections >}}",
    ),
    "kb": SectionRules(
        section="kb",
        evidence_required=True,   # for content pages; index pages may be empty
        author_field_required=False,
        type_field_value="topic",
        code_examples_policy="in_steps",
        grading_active=True,
        draft_field_required=False,
        index_shortcode="{{< children >}}",
    ),
    "products": SectionRules(
        section="products",
        evidence_required=False,
        author_field_required=False,
        type_field_value=None,
        code_examples_policy="discouraged",
        grading_active=False,
        draft_field_required=False,
        index_shortcode=None,
    ),
    "reference": SectionRules(
        section="reference",
        evidence_required=True,
        author_field_required=False,
        type_field_value=None,
        code_examples_policy="recommended",
        grading_active=True,
        draft_field_required=False,
        index_shortcode="{{< children >}}",
    ),
}


def load_section_rules(section: str) -> Optional[SectionRules]:
    """Return the SectionRules for a known section, or None if section is unknown."""
    return _SECTION_RULES.get(section)


def requires_code_warning(section: str) -> bool:
    """Return True if the section requires a warning before adding code examples."""
    rules = _SECTION_RULES.get(section)
    return rules is not None and rules.code_examples_policy == "discouraged"
