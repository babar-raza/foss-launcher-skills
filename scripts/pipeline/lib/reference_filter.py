"""
Shared API surface filtering logic for reference index generation and validation.

This module (TC-REF-09) extracts the authoritative two-step filter chain used by
batch_reference.py and check_reference_index_structure.py so both tools agree on
which api_surface.json entries appear in a grouped reference index.

Filter chain (two steps):
  Step 1 — _passes_platform_scope(): kind allowlist + path/name exclusions
  Step 2 — visibility != "internal"

TC-REF-11 (2026-06-06): Filter fully unified with batch_reference.py.  All five
platform-specific exclusions are now present in both implementations:
  1. C++  — ^I[A-Z] interface-prefix names excluded
  2. C++  — _CPP_ABSTRACT_BASES frozenset (BaseSlide, GeometryShape, …)
  3. Python — ^I[A-Z] interface-prefix names excluded
  4. Java — _JAVA_INTERNAL_CLASSES set excluded
  5. .NET — .Internal. / .internal. in class_import namespace excluded

Usage::

    from scripts.pipeline.lib.reference_filter import filter_api_surface, filtered_count

    entries = filter_api_surface(api_surface, "python")   # -> list[dict]
    count   = filtered_count(api_surface, "python")       # -> int
"""

from __future__ import annotations

import re
from typing import Sequence

_ENUM_KINDS: frozenset[str] = frozenset({
    "enum_specifier",       # C++
    "enum_declaration",     # Java / C#
    "enum_definition",      # alternative TS / C++
    "enum_item",            # Rust (no other tree-sitter grammar emits this kind)
})

# C++ abstract base classes that must not appear as public API reference pages.
# These are internal implementation bases that are not part of the public API.
_CPP_ABSTRACT_BASES: frozenset[str] = frozenset({
    "BaseSlide", "GeometryShape", "PVIObject", "GraphicalObject",
})

# Java internal implementation classes that must not appear as public API reference pages.
# These classes live in org.aspose.slides.foss.internal.* packages and were retired
# (draft: true) during the slides gap-eval sprint.  Adding them here prevents
# batch-reference from re-generating those pages on the next run.
_JAVA_INTERNAL_CLASSES: frozenset[str] = frozenset({
    "AppPropertiesPart",
    "AuthorData",
    "BaseCollection",
    "BulkTextFormat",
    "CommentAuthorsPart",
    "CommentData",
    "CommentsPart",
    "ContentTypesManager",
    "CorePropertiesPart",
    "CustomPropertiesPart",
    "ExporterBase",
    "ExporterRegistry",
    "ImageUtils",
    "LayoutSlidePart",
    "MasterReference",
    "MasterSlidePart",
    "NotesSlidePart",
    "Ns",
    "OpcPackage",
    "PptxConstants",
    "PptxExporter",
    "PptxExporterFactory",
    "PresentationPart",
    "RelationshipsManager",
    "RelsHelper",
    "ShapeFactory",
    "ShapeTypeMapping",
    "SlidePart",
    "SlideReference",
    "TableStyleMapping",
    "Template",
})

_CLASS_KINDS_BY_PLATFORM: dict[str, set[str]] = {
    "java":       {"class_declaration", "interface_declaration"},
    "net":        {"class_declaration", "interface_declaration",
                   "struct_declaration", "record_declaration"},
    "cpp":        {"class_specifier", "struct_specifier"},
    "python":     {"class_definition"},
    # TC-MT040-10: abstract_class_declaration is a distinct tree-sitter node
    # type from class_declaration (`export abstract class X {}`) -- without
    # it here, an abstract TS class extracted into api_surface.json (thanks
    # to the matching tree_helpers._CLASS_TYPES fix) would still never
    # appear in a grouped reference index, since this filter is the second,
    # independent gate reference-page generation applies.
    "typescript": {"class_declaration", "interface_declaration",
                   "type_alias_declaration", "abstract_class_declaration"},
    "javascript": {"class_declaration"},
    "nodejs":     {"class_declaration"},
    "go":         {"type_spec"},
    "rust":       {"struct_item", "enum_item", "trait_item", "union_item"},
}

# ---------------------------------------------------------------------------
# TC-MT040-17: reachability-enforcement policy (D-3)
# ---------------------------------------------------------------------------
#
# extraction/api_surface.py's RC-W1-004 "reachable" signal (see
# extraction/lang/__init__.py's module docstring for the full per-language
# adapter contract) is now consulted by reference-page generation for the
# platforms below -- an entry marked unreachable at scout time (e.g. a
# TypeScript class never re-exported through the package's resolved barrel)
# no longer gets a reference page, matching the PY-SHIM discard precedent.
# TC-MT040-42/11 built the real export_surface() barrel/entry-point resolver
# that backs this; TC-MT040-42's own wiring point started this frozenset
# empty (a deliberate no-op landing) specifically so this card could turn it
# on without also being the commit that introduces the underlying resolver.
#
# python/rust are NOT in this set: they have their own reachable signals
# (via lang.python/lang.rust's export_surface()) but enforcing them here
# would change shipped products' page counts outside of their own refresh
# runs. They are scheduled to opt in at each product's *next* refresh
# (Decision 10) -- not now, and not silently.
#
# Fail-safe: when a platform's entry point cannot be resolved (no dist/
# build output and no bare index.ts/index.tsx -- e.g. 3d/typescript's real
# clone, live-verified 2026-08-29), lang.typescript.export_surface() returns
# None and api_surface.py's _compute_reachable leaves every entry
# reachable=True for that product. This set only ever REMOVES pages relative
# to today; it can never fabricate an unreachable=True verdict from a
# resolver that gave up.
REACHABILITY_ENFORCED_PLATFORMS: "frozenset[str]" = frozenset(
    {"typescript", "javascript", "nodejs"}
)

# Bumped whenever reachability-enforcement policy changes (this card: 1 -> 2,
# enabling TS/JS/nodejs) -- mirrors GROUPED_INDEX_GENERATOR_VERSION's own
# staleness-fingerprint pattern later in this file. Not yet read by any
# consumer as a staleness trigger (that wiring is a future card); it exists
# so one exists before a second policy change needs to invalidate anything.
REFERENCE_FILTER_POLICY_VERSION = 2

# ---------------------------------------------------------------------------
# Filter implementation
# ---------------------------------------------------------------------------

_INTERNAL_PATH_MARKERS = ("/internal/", "\\internal\\", "/_internal/", "\\_internal\\")


def _passes_platform_scope(entry: dict, platform: str) -> bool:
    """Step 1 filter: kind allowlist + path/name exclusions.

    Mirrors batch_reference.py::_passes_platform_scope() exactly (TC-REF-11).

    C++ is handled with a dedicated early-return block using name-based rules
    (I-prefix and abstract bases) without path filtering, matching the generator.
    All other platforms apply the universal internal-path guard first.
    """
    kind = entry.get("kind", "")
    name = entry.get("name", "")

    # TC-MT040-42: reachability-enforcement wiring point. REACHABILITY_ENFORCED_PLATFORMS
    # starts empty (see its own docstring above) so this is a no-op for every
    # platform today -- a later card (TC-MT040-17) populates it once
    # TypeScript's real export_surface() (TC-MT040-11) exists to back the
    # scout-time "reachable" signal this reads.
    if platform in REACHABILITY_ENFORCED_PLATFORMS and entry.get("reachable") is False:
        return False

    # C++ uses name-based exclusion rules; no internal-path check.
    if platform == "cpp":
        if kind == "enum_specifier":
            return True
        if kind in ("class_specifier", "struct_specifier"):
            if re.match(r"^I[A-Z]", name):
                return False
            if name in _CPP_ABSTRACT_BASES:
                return False
            return True
        return False

    # Universal guard: classes whose source file lives under an `internal` or
    # `_internal` package segment are implementation internals, regardless of
    # platform.  PY-INIT-001: classes re-exported via a package __init__.py
    # (exported_via_package_init=True) bypass this guard — they are public API
    # despite living in _internal/.
    if not entry.get("exported_via_package_init", False):
        file_path = entry.get("file", "")
        for marker in _INTERNAL_PATH_MARKERS:
            if marker in file_path:
                return False

    # Name exclusion: private/dunder symbols (Python private).
    if name.startswith("_"):
        return False

    if platform == "python":
        if kind != "class_definition":
            return False
        if re.match(r"^I[A-Z]", name):
            return False
        return True

    if platform == "java":
        if name in _JAVA_INTERNAL_CLASSES:
            return False
        return kind in _CLASS_KINDS_BY_PLATFORM.get("java", set()) or kind in _ENUM_KINDS

    # FIX-02: .NET namespace-based internal exclusion.
    if platform == "net":
        class_import = entry.get("class_import", "")
        if ".Internal." in class_import or ".internal." in class_import:
            return False

    # TypeScript, JavaScript, nodejs, go, and any remaining platforms.
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


# ---------------------------------------------------------------------------
# Generator-version fingerprint (TC-DUPIDX-02, 2026-08-12, ST-059)
# ---------------------------------------------------------------------------
#
# Knowledge-data staleness (has api_surface.json changed?) is already tracked via
# evidence.model_sha and checked by is_stale_grouped_index() above. Generator-LOGIC staleness
# (has the code that turns api_surface.json into a grouped table improved?) had no equivalent
# signal -- a real gap: the GI-01 disambiguation fix (commit 362430210c, 2026-06-20) corrected
# generate_grouped_index()'s name-collision handling, but 9 of 30 already-published reference
# index pages kept their pre-fix duplicate rows indefinitely, because nothing ever re-derived
# them once GI-01 landed. GROUPED_INDEX_GENERATOR_VERSION closes that gap the same way
# model_sha closes the knowledge-staleness gap: a page's provenance.index_generator_version is
# stamped by generate_grouped_index() on every write; refresh_run.py's apply_run() compares it
# against the current constant and re-invokes the generator when it's behind.
#
# History:
#   1 = GI-01's Phase A case/namespace-collision disambiguation (_entry_slug() /
#       _assign_namespace_slug_suffixes()) applied unconditionally inside
#       generate_grouped_index() before _build_grouped_index_body() renders rows. No page was
#       ever stamped before this constant existed -- an absent field means "generated before
#       this fingerprint existed" and must be treated as stale, not as version 0-is-fine.
GROUPED_INDEX_GENERATOR_VERSION = 1


def index_generator_version_is_stale(
    provenance: dict | None, *, current: int = GROUPED_INDEX_GENERATOR_VERSION,
) -> bool:
    """Return True if a page's stamped generator version is behind (or absent)."""
    if not provenance:
        return True
    return (provenance.get("index_generator_version", 0) or 0) < current


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
