"""
Shared API surface filtering logic for reference index generation and validation.

This module (TC-REF-09) extracts the authoritative two-step filter chain used by
batch_reference.py and check_reference_index_structure.py so both tools agree on
which api_surface.json entries appear in a grouped reference index.

Filter chain (two steps):
  Step 1 — _passes_platform_scope(): kind allowlist + path/name exclusions
  Step 2 — visibility != "internal"

Usage::

    from scripts.pipeline.lib.reference_filter import filter_api_surface, filtered_count

    entries = filter_api_surface(api_surface, "python")   # -> list[dict]
    count   = filtered_count(api_surface, "python")       # -> int
"""

from __future__ import annotations

from typing import Sequence

# ---------------------------------------------------------------------------
# Platform-specific kind allowlists
#
# DIVERGENCE NOTE (TC-REF-11, 2026-06-03):
# This module implements the GENERAL filter chain (kind allowlist + internal
# path/name exclusions + visibility check).  batch_reference.py implements
# the same general chain PLUS four platform-specific exclusions that are NOT
# replicated here:
#   1. C++  — ^I[A-Z] interface-prefix names excluded
#   2. C++  — _CPP_ABSTRACT_BASES frozenset (BaseSlide, GeometryShape, …)
#   3. Python — ^I[A-Z] interface-prefix names excluded
#   4. Java — _JAVA_INTERNAL_CLASSES set excluded
#   5. .NET — .Internal. / .internal. in class_import namespace excluded
#
# Impact: This library returns HIGHER counts than batch_reference.py for
# affected platforms.  This is the SAFE direction — the CI staleness check
# (check_reference_index_structure.py) over-flags rather than under-flags.
# The generator (batch_reference.py) uses its own filter and produces
# correct output regardless of this library's counts.
#
# To unify: see TC-REF-11 Option A in the plan (pipeline-harden sprint).
# ---------------------------------------------------------------------------

_ENUM_KINDS: frozenset[str] = frozenset({
    "enum_specifier",       # C++
    "enum_declaration",     # Java / C#
    "enum_definition",      # alternative TS / C++
})

_CLASS_KINDS_BY_PLATFORM: dict[str, set[str]] = {
    "java":       {"class_declaration", "interface_declaration"},
    "net":        {"class_declaration", "interface_declaration",
                   "struct_declaration", "record_declaration"},
    "cpp":        {"class_specifier", "struct_specifier"},
    "python":     {"class_definition"},
    "typescript": {"class_declaration", "interface_declaration",
                   "type_alias_declaration"},
    "javascript": {"class_declaration"},
    "nodejs":     {"class_declaration"},
    "go":         {"type_spec"},
}

# ---------------------------------------------------------------------------
# Filter implementation
# ---------------------------------------------------------------------------

_INTERNAL_PATH_MARKERS = ("/internal/", "\\internal\\", "/_internal/", "\\_internal\\")


def _passes_platform_scope(entry: dict, platform: str) -> bool:
    """Step 1 filter: kind allowlist + path/name exclusions.

    Mirrors the logic in batch_reference.py::_passes_platform_scope() for the
    general (non-cpp) path.
    """
    kind = entry.get("kind", "")
    name = entry.get("name", "")
    file_path = entry.get("file", "")

    # Path exclusions: internal packages
    for marker in _INTERNAL_PATH_MARKERS:
        if marker in file_path:
            return False

    # Name exclusion: private/dunder symbols
    if name.startswith("_"):
        return False

    # Kind allowlist (platform-specific)
    class_kinds = _CLASS_KINDS_BY_PLATFORM.get(platform, set())
    return kind in class_kinds or kind in _ENUM_KINDS


def filter_api_surface(
    api_surface: Sequence[dict],
    platform: str,
) -> list[dict]:
    """Apply the full two-step filter chain to an api_surface list.

    Returns the subset of entries that should appear in a grouped reference index.

    Step 1: _passes_platform_scope() -- kind allowlist + path/name exclusions
    Step 2: visibility != "internal"
    """
    return [
        e for e in api_surface
        if _passes_platform_scope(e, platform)
        and e.get("visibility", "public") != "internal"
    ]


def filtered_count(api_surface: Sequence[dict], platform: str) -> int:
    """Return the count of entries that pass the full filter chain."""
    return sum(
        1 for e in api_surface
        if _passes_platform_scope(e, platform)
        and e.get("visibility", "public") != "internal"
    )


# ---------------------------------------------------------------------------
# Staleness helpers
# ---------------------------------------------------------------------------

def count_index_table_rows(markdown_text: str) -> int:
    """Count data rows in a markdown _index.md grouped table.

    Excludes separator rows (containing ``---``) and frontmatter.
    """
    body = markdown_text
    if markdown_text.startswith("---"):
        end = markdown_text.find("---", 3)
        if end != -1:
            body = markdown_text[end + 3:]

    count = 0
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("|") and "---" not in s and s.count("|") >= 2:
            count += 1
    return count


def is_stale_grouped_index(
    markdown_text: str,
    api_surface: Sequence[dict],
    platform: str,
    *,
    threshold: float = 0.10,
) -> tuple[bool, int, int]:
    """Return (is_stale, index_rows, expected_count).

    A grouped index is considered stale when the visible table row count is
    less than ``threshold`` fraction of the expected (filtered) entry count.

    The default threshold of 10 % is deliberately conservative so that
    legitimately curated pages that show a representative subset are not
    falsely flagged.

    Returns:
        is_stale (bool): True if the ratio is below the threshold.
        index_rows (int): Actual count of table rows in the index.
        expected (int): Filtered API entry count.
    """
    expected = filtered_count(api_surface, platform)
    rows = count_index_table_rows(markdown_text)

    if expected == 0:
        return False, rows, expected

    ratio = rows / expected
    return ratio < threshold, rows, expected
