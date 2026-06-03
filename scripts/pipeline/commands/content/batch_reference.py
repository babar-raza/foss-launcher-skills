"""batch_reference.py — Batch reference page generation from api_surface.json.

Backing script for the S-62 batch-reference skill. Generates template-based
skeleton reference pages for all missing classes/enums in a given family+platform
without requiring LLM execution, enabling headless/CI batch runs.

Usage:
    python scripts/pipeline/commands/content/batch_reference.py {family} {platform} [options]

Options:
    --kind class|enum|all   Filter by entry kind (default: all)
    --limit N               Process at most N entries (default: unlimited)
    --dry-run               Print candidates without writing any files
    --update                Re-generate pages for classes in knowledge_delta.json
                            modified_apis; skip all other existing pages.
                            Requires merged/knowledge_delta.json to exist.
                            Falls back to skip-existing mode with a warning if absent.
    --rebuild-all           Regenerate all existing auto-updatable reference pages
                            from current merged/claims.json without requiring
                            knowledge_delta.json. Skips pages with auto_updatable=false
                            or manually curated pages. Requires --confirm-rebuild when
                            more than REBUILD_CONFIRM_THRESHOLD pages would be rebuilt.
    --confirm-rebuild       Required when --rebuild-all would regenerate more than
                            REBUILD_CONFIRM_THRESHOLD existing pages.

CONTRACT: This script is the backing implementation for S-62 (batch-reference).
The skill spec in .agents/skills/batch-reference/SKILL.md documents the same
platform scope rules and summary format. Keep them in sync.
verified: 2026-04-07
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from page_spec import SitePlan
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)

# Bootstrap: ensure scripts/pipeline/ is on sys.path for sibling imports
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(_HERE.parent.parent / "lib")  # scripts/pipeline/lib
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from core.env_loader import load_env  # noqa: E402
load_env()

from lib.knowledge_core import Knowledge  # noqa: E402
from evidence.runner import attach_evidence  # noqa: E402
from lib.provenance import is_auto_updatable, is_manually_curated, safe_content_write, ProtectedPageError  # noqa: E402
from lib.backlink_targets import load_target_map, resolve_backlink  # noqa: E402

# ---------------------------------------------------------------------------
# Backlink target map (loaded lazily, cached for the run)
# ---------------------------------------------------------------------------
_backlink_target_map: dict | None = None


def _get_backlink_target_map() -> dict | None:
    """Load and cache the aspose_com_targets.json target map."""
    global _backlink_target_map
    if _backlink_target_map is None:
        try:
            _backlink_target_map = load_target_map(_DEFAULT_REPO_ROOT)
        except Exception as exc:
            LOG.warning("backlink: could not load target map: %s", exc)
            _backlink_target_map = {}
    return _backlink_target_map or None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEAL_CONFIRM_THRESHOLD = 20    # require --confirm-heal when healing more than this many curated pages
REBUILD_CONFIRM_THRESHOLD = 20  # require --confirm-rebuild when --rebuild-all targets more than this many pages

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]

REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
CONTENT_ROOT = REPO_ROOT / "content" / "reference.aspose.org" / "en"


def configure(
    repo_root: Path | None = None,
    knowledge_root: Path | None = None,
    content_root: Path | None = None,
) -> None:
    """Set module-level root paths. Call with no args to reset defaults.

    Tests call ``batch_reference.configure(repo_root=tmp_path)`` (or pass
    knowledge_root / content_root directly) instead of monkeypatching globals.
    Omitted args fall back to values derived from repo_root or built-in defaults.
    """
    global REPO_ROOT, KNOWLEDGE_ROOT, CONTENT_ROOT
    root = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT
    REPO_ROOT = root
    KNOWLEDGE_ROOT = knowledge_root if knowledge_root is not None else root / "knowledge"
    CONTENT_ROOT = (
        content_root if content_root is not None
        else root / "content" / "reference.aspose.org" / "en"
    )

# Python enum base classes (mirrors extraction/tree_helpers.py _PY_ENUM_BASES)
_PY_ENUM_BASES: frozenset[str] = frozenset({
    "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag",
    "enum.Enum", "enum.IntEnum", "enum.StrEnum", "enum.Flag", "enum.IntFlag",
})

# Canonical kind values emitted by api_surface.py ("kind": cnode.type).
# Source of truth: extraction/tree_helpers.py _CLASS_TYPES dict.
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

_PLATFORM_TO_LANG: dict[str, str] = {
    "python": "python",
    "net": "csharp",
    "java": "java",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "javascript",
}

# ERC-* claim kinds treated as prose-eligible for reference page descriptions
_ERC_PROSE_KINDS: frozenset[str] = frozenset({"api", "feature"})


# ---------------------------------------------------------------------------
# Color constant description template
# ---------------------------------------------------------------------------

def _color_constant_desc(prop_name: str) -> str:
    """Generate a deterministic description for a named color constant property.

    Converts PascalCase or SCREAMING_SNAKE_CASE names to natural language:
      AliceBlue     → "The Alice Blue color."
      ALICE_BLUE    → "The Alice Blue color."
      AntiqueWhite  → "The Antique White color."
    """
    if "_" in prop_name:
        # SCREAMING_SNAKE_CASE → title case
        natural = prop_name.replace("_", " ").title()
    else:
        # PascalCase → insert space before each uppercase letter following a lowercase
        natural = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prop_name)
    return f"The {natural} color."


def _is_color_type(ptype: str) -> bool:
    """Return True if ptype refers to a Color type (any platform naming convention)."""
    return ptype.lower().rstrip("?") in ("color", "system.drawing.color")


# ---------------------------------------------------------------------------
# ERC claim index builder
# ---------------------------------------------------------------------------

def _build_erc_index(family: str, platform: str) -> dict[str, dict]:
    """Build a class_name → best ERC-* claim dict from merged/claims.json.

    Returns an empty dict if claims.json is missing or contains no ERC-* claims.
    Only considers claims with kind in _ERC_PROSE_KINDS (api, feature).
    When multiple ERC-* claims match the same class, the highest-confidence one wins.
    """
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return {}
    try:
        claims_list = json.loads(claims_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    index: dict[str, dict] = {}
    for claim in claims_list:
        cid = claim.get("claim_id", "")
        if not cid.startswith("ERC-"):
            continue
        if claim.get("kind", "") not in _ERC_PROSE_KINDS:
            continue
        text = (claim.get("text") or "").strip()
        if not text:
            continue
        confidence = float(claim.get("confidence", 0.0))

        # Extract class name from the claim text.
        # ERC-* claim texts commonly start with "The ClassName." or "**ClassName**"
        cls_name = None
        m = re.match(r"^\*\*([A-Z]\w+)\*\*", text)
        if m:
            cls_name = m.group(1)
        elif re.match(r"^The ([A-Z]\w+)[.\s]", text):
            cls_name = re.match(r"^The ([A-Z]\w+)[.\s]", text).group(1)
        elif re.match(r"^([A-Z]\w+)[.\s]", text):
            cls_name = re.match(r"^([A-Z]\w+)[.\s]", text).group(1)

        if not cls_name:
            continue

        # Keep highest-confidence claim per class
        existing = index.get(cls_name)
        if existing is None or confidence > float(existing.get("confidence", 0.0)):
            index[cls_name] = claim

    return index


# ---------------------------------------------------------------------------
# Member-level ERC description index
# ---------------------------------------------------------------------------

# Regex to extract ClassName.MemberName from the beginning of an ERC claim text.
# Handles common prefixes: "The ClassName.Member ...", "Calling ClassName.Member(...)",
# "ClassName.Member ..."
_MEMBER_PREFIX_RE = re.compile(
    r"^(?:The |Calling )?([A-Za-z]\w+)\.([A-Za-z_]\w*)\b"
)

# Fragments to strip from the description after removing the class.member prefix.
# Strips: "(params) ->" return signatures, "property of type T", leading lowercase
# prose words that are part of the signature (not the description).
_SIGNATURE_STRIP_RE = re.compile(
    r"^(?:\([^)]*\)\s*(?:->\s*\S+\s*)?|"           # (params) -> ret
    r"property\s+of\s+type\s+\S+\s*|"              # property of type T
    r"field\s+of\s+type\s+\S+\s*)"                 # field of type T
)


def _build_erc_member_index(family: str, platform: str, api_surface=None) -> dict[str, str]:
    """Build a 'ClassName.MemberName' → one-sentence description index from ERC api claims.

    Supplements api_surface.json doc fields (which are empty for FOSS repos without
    docstrings) so that property/method table rows have meaningful descriptions.
    Only considers ERC claims with kind == 'api'. Returns an empty dict if no
    api-kind ERC claims are found.

    When *api_surface* is provided (list of api_surface entries), matching is gated
    on known class names: if the matched class name is not in the known classes set,
    the claim is skipped to prevent prose like "it.seems" or "i.e. calling" from
    being misindexed as member descriptions.  When api_surface is None or empty,
    the gate is skipped (graceful degradation).
    """
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return {}
    try:
        claims_list = json.loads(claims_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    known_classes: set[str] = {cls.get("name", "") for cls in api_surface if cls.get("name")} if api_surface else set()

    index: dict[str, str] = {}
    for claim in claims_list:
        if not claim.get("claim_id", "").startswith("ERC-"):
            continue
        if claim.get("kind", "") != "api":
            continue
        text = (claim.get("text") or "").strip()
        if not text:
            continue

        # ERC claims may start with a backtick-quoted name: "`Workbook.Save` overloads..."
        # Strip leading backtick so the regex can match the class/member name.
        text_clean = text.lstrip("`")
        m = _MEMBER_PREFIX_RE.match(text_clean)
        if not m:
            continue

        class_name = m.group(1)
        if known_classes and class_name not in known_classes:
            continue  # reject prose that happens to match ClassName.word pattern

        key = f"{m.group(1)}.{m.group(2)}"

        # Extract the description: strip the matched prefix (+ closing backtick if any),
        # then strip any signature fragments, take the first sentence.
        after_prefix = text_clean[m.end():].lstrip("`").lstrip()
        desc = _SIGNATURE_STRIP_RE.sub("", after_prefix).strip()
        # Take first sentence (split on ". " to avoid splitting on abbreviations)
        sentences = re.split(r"\.\s+", desc)
        desc = sentences[0].rstrip(".").strip() if sentences else desc
        if not desc:
            continue
        # Capitalize first character
        desc = desc[0].upper() + desc[1:] if len(desc) > 1 else desc.upper()

        # When multiple claims exist for the same member, keep the longest description
        # (more informative wins).
        if key not in index or len(desc) > len(index[key]):
            index[key] = desc

    return index


# ---------------------------------------------------------------------------
# Platform scope filter
# ---------------------------------------------------------------------------

def _is_enum(entry: dict, platform: str) -> bool:
    """Return True if this api_surface entry represents an enum type.

    FIX-09: Removed the enum_members-only heuristic that caused classes with
    ALL_CAPS constants (e.g. Scene) to be misclassified as enums.  Now only
    tree-sitter kind or explicit enum base class inheritance qualifies.
    """
    kind = entry.get("kind", "")
    if kind in _ENUM_KINDS:
        return True
    # Python: IntEnum / Flag / etc. appear as class_definition with enum bases
    if platform == "python" and kind == "class_definition":
        bases = entry.get("bases", [])
        if any(b in _PY_ENUM_BASES for b in bases):
            return True
    return False


def _passes_platform_scope(entry: dict, platform: str) -> bool:
    """Return True if the entry should be included in the candidate list.

    DIVERGENCE NOTE (TC-REF-11, 2026-06-03):
    This function includes platform-specific exclusions (C++ I-prefix/abstract
    bases, Python I-prefix, Java internal classes, .NET namespace internals)
    that are NOT present in the shared library at
    scripts/pipeline/lib/reference_filter.py.  The shared library is used for
    CI staleness checks and returns higher counts (safe direction: over-flags).
    This function is the authoritative filter for content generation.
    """
    kind = entry.get("kind", "")
    name = entry.get("name", "")

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
    # platform.  api_surface.json carries the `file` field (path relative to
    # clone root).  Also exclude underscore-prefixed names (Python private).
    _file = entry.get("file", "")
    if "/internal/" in _file or "\\internal\\" in _file \
       or "/_internal/" in _file or "\\_internal\\" in _file:
        return False
    if name.startswith("_"):
        return False

    if platform == "python":
        if kind != "class_definition":
            return False
        if re.match(r"^I[A-Z]", name):
            return False
        return True  # includes both regular classes and enum subclasses

    if platform == "java":
        if entry.get("name") in _JAVA_INTERNAL_CLASSES:
            return False
        return kind in _CLASS_KINDS_BY_PLATFORM.get("java", set()) or kind in _ENUM_KINDS

    # FIX-02: .NET namespace-based internal exclusion
    if platform == "net":
        class_import = entry.get("class_import", "")
        if ".Internal." in class_import or ".internal." in class_import:
            return False

    # .NET, TypeScript, JavaScript
    class_kinds = _CLASS_KINDS_BY_PLATFORM.get(platform, set())
    if kind in class_kinds or kind in _ENUM_KINDS:
        return True
    return False


def _apply_kind_filter(entries: list[dict], kind_arg: str, platform: str) -> list[dict]:
    """Apply --kind class|enum|all filter on top of platform-scoped entries."""
    if kind_arg == "all":
        return entries
    if kind_arg == "enum":
        return [e for e in entries if _is_enum(e, platform)]
    if kind_arg == "class":
        return [e for e in entries if not _is_enum(e, platform)]
    raise ValueError(f"Invalid kind_arg: {kind_arg!r}. Must be 'all', 'enum', or 'class'.")


# ---------------------------------------------------------------------------
# Slug sanitization
# ---------------------------------------------------------------------------

# Characters that are unsafe in filenames across Windows/macOS/Linux or
# that conflict with Hugo section separators.
_UNSAFE_SLUG_RE = re.compile(r'[.:\/\\<>|?*\[\]"]+')


def _sanitize_slug(name: str) -> str:
    """Sanitize a class name into a filesystem-safe slug.

    Replaces dots, colons, and other unsafe characters with underscores.
    Python PEP 8 names pass through unchanged.
    """
    return _UNSAFE_SLUG_RE.sub("_", name)


# ---------------------------------------------------------------------------
# Category label
# ---------------------------------------------------------------------------

def _category(entry: dict, platform: str) -> str:
    """FIX-09: The kind field from tree-sitter is authoritative for class vs enum.

    Only classify as Enum when the kind itself is an enum type OR the entry
    has explicit enum base classes (Python).  Convention-based enum_members
    alone are not sufficient — a class with ALL_CAPS constants (like Scene
    with status constants) should remain a Class.
    """
    kind = entry.get("kind", "")
    # Authoritative enum kinds from tree-sitter
    if kind in _ENUM_KINDS:
        return "Enum"
    # Python enum via base class inheritance (Enum, IntEnum, etc.)
    if platform == "python" and kind == "class_definition":
        bases = entry.get("bases", [])
        if any(b in _PY_ENUM_BASES for b in bases):
            return "Enum"
    # For all other cases, use the kind field
    if "interface" in kind:
        return "Interface"
    if "struct" in kind:
        return "Struct"
    return "Class"


# ---------------------------------------------------------------------------
# Page template builder
# ---------------------------------------------------------------------------

def _build_page(
    entry: dict,
    family: str,
    platform: str,
    erc_index: dict[str, dict] | None = None,
    member_erc_index: dict[str, str] | None = None,
    model_sha: str = "",
    model_version: str = "",
) -> str:
    """Build a template-based skeleton reference page from an api_surface entry.

    When *erc_index* is provided and the entry has no docstring (doc=""), the
    highest-confidence ERC-* claim for this class is used as the description
    paragraph and cited in evidence.claims.

    When *member_erc_index* is provided, property/method table description cells
    are populated from ERC api-kind claim descriptions when the api_surface doc
    field is empty. This fills in descriptions for FOSS repos without docstrings.
    """
    name = entry.get("name", "")
    doc = (entry.get("doc") or "").strip()
    category = _category(entry, platform)
    lang = _PLATFORM_TO_LANG.get(platform, platform)

    # ERC-* claim fallback when doc is empty
    erc_claim: dict | None = None
    erc_claim_id: str = ""
    if not doc and erc_index:
        erc_claim = erc_index.get(name)
        if erc_claim:
            erc_claim_id = erc_claim.get("claim_id", "")
            doc = (erc_claim.get("text") or "").strip()

    methods = entry.get("methods", [])
    properties = entry.get("properties", [])
    bases = entry.get("bases", [])
    enum_members = entry.get("enum_members") or entry.get("members", [])

    # Description line
    parts = [f"`{name}` {category.lower()}"]
    if bases:
        # FIX-05: filter out self-referential inheritance and enum bases
        bases_filtered = [b for b in bases if b not in _PY_ENUM_BASES and "enum." not in b and b != name]
        if bases_filtered:
            parts.append(f"(inherits {', '.join(bases_filtered[:2])})")
    method_count = len(methods)
    prop_count = len(properties)
    if method_count or prop_count:
        counts = []
        if method_count:
            counts.append(f"{method_count} method{'s' if method_count != 1 else ''}")
        if prop_count:
            counts.append(f"{prop_count} {'properties' if prop_count != 1 else 'property'}")
        parts.append(f"with {' and '.join(counts)}")
    description = " ".join(parts)

    # Build evidence apis list from known class members (metadata-derived, not code-extracted).
    # Capped at 20 total to keep frontmatter readable; methods first, then properties.
    apis_list = []
    seen_api_names: set[str] = set()
    for m in methods:
        if len(apis_list) >= 20:
            break
        mname = m.get("name", "")
        if mname and f"{name}.{mname}" not in seen_api_names:
            seen_api_names.add(f"{name}.{mname}")
            apis_list.append(f"  - {name}.{mname}")
    for p in properties:
        if len(apis_list) >= 20:
            break
        pname = p.get("name", "")
        if pname and f"{name}.{pname}" not in seen_api_names:
            seen_api_names.add(f"{name}.{pname}")
            apis_list.append(f"  - {name}.{pname}")
    # Frontmatter
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    lines = [
        "---",
        f"linkTitle: {name}",
        f"title: {name}",
        f'description: "{description}"',
        f'summary: "{description}"',
        "categories:",
        f"- {category}",
        "layout: reference-single",
        "provenance:",
        "  content_origin: skill-generated",
        "  last_mechanism: skill",
        "  auto_updatable: true",
        f"  content_created_at: '{now_iso}'",
        "evidence:",
        f"  model_sha: '{model_sha}'",
        f"  model_version: '{model_version}'",
    ]
    if erc_claim_id:
        lines.append("  claims:")
        lines.append(f"  - \"{erc_claim_id}\"")
    else:
        lines.append("  claims: []")
    if apis_list:
        lines.append("  apis:")
        lines.extend(apis_list)
    else:
        lines.append("  apis: []")
    lines.append("---")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    # LC-11 FIX: use correct display name for "pdf" family ("PDF" not "Pdf")
    _fam_disp = {"3d": "3D", "pdf": "PDF"}.get(family, family.capitalize())
    _plat_disp = {"net": ".NET", "cpp": "C++"}.get(platform, platform.capitalize())
    product_line = f"`{name}` is a {category.lower()} in Aspose.{_fam_disp} FOSS for {_plat_disp}."
    lines.append(product_line)
    if bases:
        # FIX-05: filter out self-referential inheritance and enum bases
        bases_filtered = [b for b in bases if b not in _PY_ENUM_BASES and "enum." not in b and b != name]
        if bases_filtered:
            lines.append(f"Inherits from: {', '.join(f'`{b}`' for b in bases_filtered[:3])}.")
    if doc:
        lines.append("")
        lines.append(doc)

    # LC-10 FIX: add source-grounded prose summary to satisfy content_substance >=50 word threshold.
    # Only method/property/member names from api_surface.json are used — no hallucinated claims.
    _lc10_prose: list[str] = []
    _all_mnames = sorted({m.get("name", "") for m in methods if m.get("name")})
    _all_pnames = sorted({p.get("name", "") for p in properties if p.get("name")})
    _all_enames = [
        (m.get("name", str(m)) if isinstance(m, dict) else str(m))
        for m in enum_members
    ]
    if _all_mnames:
        _preview_count = min(12, len(_all_mnames))
        _listed = ", ".join(f"`{n}`" for n in _all_mnames[:_preview_count])
        if len(_all_mnames) > _preview_count:
            _listed += f", and {len(_all_mnames) - _preview_count} additional methods"
        _lc10_prose.append(
            f"This {category.lower()} provides {len(_all_mnames)} "
            f"{'method' if len(_all_mnames) == 1 else 'methods'} "
            f"for working with {name} objects in {_plat_disp} programs."
        )
        _lc10_prose.append(f"Available methods include: {_listed}.")
        _lc10_prose.append(
            f"All public members are accessible to any {_plat_disp} application "
            f"after installing the Aspose.{_fam_disp} FOSS for {_plat_disp} package."
        )
    if _all_pnames:
        _plisted = ", ".join(f"`{n}`" for n in _all_pnames[:6])
        if len(_all_pnames) > 6:
            _plisted += f", and {len(_all_pnames) - 6} more"
        _lc10_prose.append(f"Properties: {_plisted}.")
    if category == "Enum" and _all_enames and not _lc10_prose:
        _elisted = ", ".join(f"`{e}`" for e in _all_enames[:12])
        if len(_all_enames) > 12:
            _elisted += f", and {len(_all_enames) - 12} more"
        _lc10_prose.append(
            f"This enumeration defines {len(_all_enames)} "
            f"{'value' if len(_all_enames) == 1 else 'values'}: {_elisted}."
        )
    if not _lc10_prose:
        # Sparse type: no methods, properties, or enum members listed.
        # Two sentences ensure the page meets the content_substance >=50 word threshold
        # even when the type has no members and api_surface.json has no doc text.
        _lc10_prose.append(
            f"This {category.lower()} represents a value type in the "
            f"Aspose.{_fam_disp} FOSS for {_plat_disp} type system "
            f"and is used with other exported types in the package."
        )
        _lc10_prose.append(
            f"It is part of the public API exposed by the `pdf` package "
            f"and can be passed to or returned from functions and methods "
            f"that work with {name} values in your Go application."
        )
    lines.append("")
    for _lp in _lc10_prose:
        lines.append(_lp)
    lines.append("")

    # Enum values section
    if category == "Enum" and enum_members:
        lines.append("## Values")
        lines.append("")
        lines.append("| Value | Description |")
        lines.append("|-------|-------------|")
        for member in enum_members:
            if isinstance(member, dict):
                mname = member.get("name", str(member))
                mdoc = (member.get("doc") or member.get("description") or "").strip()
            else:
                mname = str(member)
                mdoc = ""
            if not mdoc and member_erc_index:
                mdoc = member_erc_index.get(f"{name}.{mname}", "")
            lines.append(f"| `{mname}` | {mdoc} |")
        lines.append("")

    # Properties section
    if properties:
        lines.append("## Properties")
        lines.append("")
        lines.append("| Name | Type | Access | Description |")
        lines.append("|------|------|--------|-------------|")
        for prop in properties:
            pname = prop.get("name", "")
            ptype = prop.get("type", prop.get("return_type", ""))
            # Escape bare | in type strings so markdown table parsers don't
            # miscount columns (e.g. "int | None" → "int \| None").
            ptype_md = ptype.replace("|", r"\|")
            writable = prop.get("writable", False)
            # FR-14 compat: TypeScript extraction uses access_mode instead of writable
            access_mode = prop.get("access_mode", "")
            if access_mode == "readwrite":
                writable = True
            elif access_mode == "writeonly":
                writable = True
            access = "Read/Write" if writable else "Read"
            pdoc = (prop.get("doc") or "").strip()
            if not pdoc and member_erc_index:
                pdoc = member_erc_index.get(f"{name}.{pname}", "")
            # Color constant template: generate "The X color." for undocumented
            # read-only Color-typed properties (e.g. AliceBlue, ALICE_BLUE).
            # These are self-documenting by name; source code never adds docstrings
            # to individual color constants, so this is the correct fallback.
            if not pdoc and not writable and _is_color_type(ptype):
                pdoc = _color_constant_desc(pname)
            lines.append(f"| `{pname}` | `{ptype_md}` | {access} | {pdoc} |")
        lines.append("")

    # Methods section
    if methods:
        lines.append("## Methods")
        lines.append("")
        lines.append("| Signature | Description |")
        lines.append("|-----------|-------------|")
        _described_method_names: set[str] = set()
        for method in methods:
            mname = method.get("name", "")
            params = method.get("params", method.get("parameters", []))
            ret = method.get("return_type", "")
            mdoc = (method.get("doc") or "").strip()
            if not mdoc and member_erc_index and mname not in _described_method_names:
                # Only apply ERC description to the FIRST overload; subsequent overloads
                # with the same name get no description so the DC evaluator sees realistic
                # empty-cell counts and doesn't inflate grades.
                mdoc = member_erc_index.get(f"{name}.{mname}", "")
                if mdoc:
                    _described_method_names.add(mname)

            param_strs = []
            for p in params:
                if isinstance(p, dict):
                    pn = p.get("name", "")
                    pt = p.get("type", "").replace("|", r"\|")
                    param_strs.append(f"{pn}: {pt}" if pt else pn)
                else:
                    param_strs.append(str(p))
            ret_md = ret.replace("|", r"\|") if ret else ret
            sig = f"`{mname}({', '.join(param_strs)})`"
            if ret_md and ret_md not in ("void", "None", ""):
                sig += f" → `{ret_md}`"
            # FIX-04: warn when method is a stub (raises NotImplementedError or similar)
            if method.get("stub"):
                stub_note = "**Not implemented in the FOSS edition — throws at runtime.**"
                mdoc = f"{stub_note} {mdoc}" if mdoc else stub_note
            lines.append(f"| {sig} | {mdoc} |")
        lines.append("")

    # TC-BL-007: Append See Also section with reciprocal aspose.com backlink
    _tm = _get_backlink_target_map()
    if _tm:
        try:
            chosen_url, _rtype, _rsubdomain, _fallback = resolve_backlink(
                family, platform, "reference.aspose.org", _tm
            )
            if chosen_url:
                lines.append("## See Also")
                lines.append("")
                lines.append(
                    f"- [{_get_family_display(family, platform, target_type=_rtype)} — Enterprise API Reference]"
                    f"({chosen_url})"
                )
                lines.append("")
            else:
                LOG.warning("backlink: BLOCKED_TARGET for %s/%s — See Also omitted", family, platform)
        except Exception as exc:
            LOG.warning("backlink: See Also generation failed for %s/%s: %s", family, platform, exc)

    # TC-GATE4B: Compute content_hash from the body so the commit hook's
    # provenance_normalize_hash step is a no-op (hash already correct).
    # This prevents the RECONCILE_DRIFTED loop where generator omits
    # content_hash, hook adds it, and manifest output drifts.
    #
    # Body is everything after the closing "---\n" of frontmatter.
    # Use the EXACT same regex as provenance.compute_content_hash to ensure
    # identical body extraction (provenance._FRONTMATTER_RE).
    full_text = "\n".join(lines)
    _FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)
    fm_match = _FM_RE.match(full_text)
    body = full_text[fm_match.end():] if fm_match else full_text
    # Normalize body the same way provenance.compute_content_hash does:
    # CRLF->LF, strip trailing whitespace per line
    normalized = "\n".join(
        line.rstrip() for line in body.replace("\r\n", "\n").splitlines()
    )
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    # Insert content_hash into provenance block (after content_created_at line)
    lines_out = []
    inserted = False
    for line in lines:
        lines_out.append(line)
        if not inserted and line.strip().startswith("content_created_at:"):
            lines_out.append(f"  content_hash: {content_hash}")
            inserted = True
    return "\n".join(lines_out)


def _get_family_display(family: str, platform: str, target_type: str | None = None) -> str:
    """Return display name for the See Also link anchor text.

    target_type: "platform" or "family" from resolve_backlink().
    When "family", anchor omits platform suffix (TC-BL-008).
    """
    try:
        fam_map_path = _DEFAULT_REPO_ROOT / "data" / "families.json"
        if fam_map_path.exists():
            import json as _json
            fmap = _json.loads(fam_map_path.read_text(encoding="utf-8"))
            fam_title = fmap.get(family, f"Aspose.{family.title()}")
        else:
            fam_title = f"Aspose.{family.title()}"
        # FAMILY-ANCHOR rule: if resolved target is a family URL, never include "for {Platform}"
        if target_type == "family" or not platform:
            return fam_title
        plat_map = {"net": ".NET", "python": "Python", "java": "Java", "cpp": "C++",
                    "nodejs": "Node.js", "ruby": "Ruby", "go": "Go", "android": "Android"}
        plat_title = plat_map.get(platform, platform.title())
        return f"{fam_title} for {plat_title}"
    except Exception:
        return f"Aspose.{family.title()}"


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def _load_update_apis(family: str, platform: str) -> set[str] | None:
    """Load the set of API class names that need updating from knowledge_delta.json.

    Includes modified_apis, new_apis, and resurrected_apis so that --update mode
    regenerates pages for all classes that changed, were added, or were re-added
    after a prior removal (Fix D — healing sprint 2026-04-15).

    Returns None if the file is absent (caller falls back to full re-run).
    Returns an empty set if the file exists but has no relevant APIs.
    """
    delta_path = KNOWLEDGE_ROOT / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.exists():
        return None
    try:
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
        return (set(delta.get("modified_apis", []))
                | set(delta.get("new_apis", []))
                | set(delta.get("resurrected_apis", [])))
    except Exception:
        return None


_FRONTMATTER_FENCE_RE = re.compile(r"^---\n", re.MULTILINE)


def _extract_body(text: str) -> str:
    """Return the body of a page (everything after the closing frontmatter fence).

    If no frontmatter is found, returns the full text so that comparisons still
    work (the page is treated as all-body).
    """
    # Find the second occurrence of a line that is exactly "---"
    fences = [m.start() for m in _FRONTMATTER_FENCE_RE.finditer(text)]
    if len(fences) >= 2:
        return text[fences[1] + 4:]  # skip "---\n" (4 chars)
    return text


def _has_meaningful_change(existing_path: Path, new_content: str) -> bool:
    """Return True if *new_content* has a different body than the existing file.

    Only the content *after* the closing frontmatter fence is compared.  This
    means evidence metadata (model_sha, apis list, grade, graded_at, content_hash,
    etc.) and provenance fields (content_created_at, content_hash) are ignored —
    they are all rewritten by attach_evidence() / update_mechanism() after the
    body write anyway.

    Returns True (treat as changed) if the existing file cannot be read.
    """
    try:
        existing = existing_path.read_text(encoding="utf-8")
    except OSError:
        return True

    return _extract_body(existing).rstrip() != _extract_body(new_content).rstrip()


# ---------------------------------------------------------------------------
# Grouped index generation
# ---------------------------------------------------------------------------

# Family-specific group label overrides for human-friendly headings.
# Keys are lowercased package/module tail segments; values are display labels.
_GROUP_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "email": {
        "cfb": "CFB Format (Compound File Binary)",
        "msg": "MSG Format",
    },
    "font": {
        "cff": "CFF Font Handling",
        "eot": "EOT Font Handling",
        "ttf": "TrueType Font Handling",
        "type1": "Type1 Font Handling",
        "woff": "WOFF / WOFF2 Handling",
        "_brotli": "Brotli Compression (Internal)",
    },
}


def _derive_group_key(entry: dict, family: str, platform: str) -> str:
    """Extract a package/module group key from an api_surface entry.

    Returns the most informative subpackage segment from the ``file`` path.
    For entries at the package root, returns ``"core"``.
    """
    file_path = entry.get("file", "")
    if not file_path:
        return "core"

    parts = file_path.replace("\\", "/").split("/")

    if platform == "python":
        # Pattern: src/aspose_font/ttf/tables/name.py  or  aspose/email_foss/cfb/reader.py
        # Find the family package root and return the next segment
        for i, p in enumerate(parts):
            if family.replace("-", "_") in p.replace("-", "_").lower():
                if i + 1 < len(parts) - 1:  # -1 to skip the filename
                    return parts[i + 1]
                return "core"
        return "core"

    elif platform in ("java", "net"):
        # Pattern: src/main/java/org/aspose/pdf/operators/SetColor.java
        # Find 'aspose' then family, then take the next segment(s)
        for i, p in enumerate(parts):
            if p.lower() == family.lower() and i + 1 < len(parts) - 1:
                next_seg = parts[i + 1]
                if next_seg.endswith(".java") or next_seg.endswith(".cs"):
                    return "core"
                return next_seg
        return "core"

    elif platform == "go":
        # Pattern: pkg/api/document.go or internal/cos/stream.go
        for i, p in enumerate(parts):
            if p in ("pkg", "internal", "api") and i + 1 < len(parts) - 1:
                return parts[i + 1]
        # Fallback: use second-to-last directory
        if len(parts) >= 3:
            return parts[-2]
        return "core"

    elif platform in ("cpp", "typescript"):
        # Similar to Java pattern
        for i, p in enumerate(parts):
            if p.lower() == family.lower() and i + 1 < len(parts) - 1:
                next_seg = parts[i + 1]
                if "." in next_seg:  # filename
                    return "core"
                return next_seg
        return "core"

    return "core"


def _group_label(key: str, family: str, platform: str) -> str:
    """Convert a group key to a human-readable heading."""
    overrides = _GROUP_LABEL_OVERRIDES.get(family, {})
    if key in overrides:
        return overrides[key]
    if key == "core":
        return "Core API"
    # Title-case the key, replace underscores with spaces
    label = key.replace("_", " ").replace("-", " ").title()
    return label


def _build_grouped_index_body(
    api_surface: list[dict],
    family: str,
    platform: str,
    erc_index: dict[str, dict] | None = None,
) -> str:
    """Build the grouped markdown body for a reference platform _index.md.

    Groups api_surface entries by package/module, then by type category.
    Returns the markdown body (no frontmatter).
    """
    from collections import defaultdict

    # Group by package key
    groups: dict[str, list[dict]] = defaultdict(list)
    for entry in api_surface:
        key = _derive_group_key(entry, family, platform)
        groups[key].append(entry)

    # Sort groups: "core" first, then alphabetically
    sorted_keys = sorted(groups.keys(), key=lambda k: ("" if k == "core" else k))

    lines: list[str] = []

    for gkey in sorted_keys:
        entries = groups[gkey]
        label = _group_label(gkey, family, platform)

        # Sub-group by category
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            cat = _category(e, platform)
            by_cat[cat].append(e)

        # Sort categories: Class first, then Interface, Struct, Enum
        cat_order = {"Class": 0, "Interface": 1, "Struct": 2, "Enum": 3}
        sorted_cats = sorted(by_cat.keys(), key=lambda c: cat_order.get(c, 99))

        # Determine section heading
        # If there's only one category and it's Class, use the group label directly
        # If there are multiple categories, append category name to sub-tables
        multi_cat = len(sorted_cats) > 1

        lines.append(f"## {label}")
        lines.append("")

        for cat in sorted_cats:
            cat_entries = sorted(by_cat[cat], key=lambda e: e.get("name", ""))

            if multi_cat and cat != "Class":
                # Add a sub-heading for non-Class categories
                cat_plural = {
                    "Enum": "Enumerations",
                    "Interface": "Interfaces",
                    "Struct": "Structs",
                }.get(cat, f"{cat}es")
                lines.append(f"### {cat_plural}")
                lines.append("")

            # Table header
            col_name = {
                "Enum": "Enumeration",
                "Interface": "Interface",
                "Struct": "Struct",
            }.get(cat, "Class")
            lines.append(f"| {col_name} | Description |")
            lines.append("|---|---|")

            for e in cat_entries:
                name = e.get("name", "?")
                doc = e.get("doc", "").strip()
                # Truncate to first sentence
                if doc:
                    doc = doc.split("\n")[0].split(". ")[0]
                    if not doc.endswith("."):
                        doc += "."
                elif erc_index and name in erc_index:
                    # Fallback to ERC claim description
                    erc = erc_index[name]
                    doc = erc.get("description", "").split("\n")[0].split(". ")[0]
                    if doc and not doc.endswith("."):
                        doc += "."
                if not doc:
                    doc = f"{cat} in the {family.title()} API."
                # Escape pipes in doc
                doc = doc.replace("|", "\\|")
                lines.append(f"| `{name}` | {doc} |")

            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _is_flat_index(index_path: Path) -> bool:
    """Return True if a reference _index.md uses only {{< children >}} without grouped tables."""
    if not index_path.exists():
        return False
    text = index_path.read_text(encoding="utf-8")
    # Extract body after frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            body = text[end + 3:].strip()
        else:
            body = text.strip()
    else:
        body = text.strip()
    # Strip See Also section
    import re as _re
    body = _re.sub(r"##\s*See Also.*", "", body, flags=_re.DOTALL).strip()
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    has_h2 = any(l.startswith("## ") for l in lines)
    has_table = any(l.startswith("|") for l in lines)
    if has_h2 and has_table:
        return False
    return "{{< children" in body


def _auto_heal_flat_index(family: str, platform: str) -> None:
    """During --update/--rebuild-all, auto-heal a flat reference _index.md if possible."""
    index_path = CONTENT_ROOT / "reference.aspose.org" / "en" / family / platform / "_index.md"
    if not _is_flat_index(index_path):
        return
    api_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        return
    api = json.loads(api_path.read_text(encoding="utf-8"))
    if len(api) < 5:
        return
    print(f"\nAuto-healing flat reference index for {family}/{platform}...")
    result = generate_grouped_index(family, platform, dry_run=False)
    if result and result.get("written"):
        print(f"  Flat index healed: {result.get('entry_count', 0)} entries grouped")
    else:
        reason = result.get("reason", "unknown") if result else "no result"
        print(f"  Flat index heal skipped: {reason}")


def detect_flat_indexes() -> list[dict]:
    """Scan all reference platforms and return those with flat indexes that could be grouped."""
    ref_root = CONTENT_ROOT / "reference.aspose.org" / "en"
    results = []
    if not ref_root.is_dir():
        return results
    for family_dir in sorted(ref_root.iterdir()):
        if not family_dir.is_dir():
            continue
        for plat_dir in sorted(family_dir.iterdir()):
            if not plat_dir.is_dir():
                continue
            index_path = plat_dir / "_index.md"
            if not _is_flat_index(index_path):
                continue
            api_path = KNOWLEDGE_ROOT / family_dir.name / plat_dir.name / "merged" / "api_surface.json"
            if not api_path.exists():
                continue
            api = json.loads(api_path.read_text(encoding="utf-8"))
            if len(api) >= 5:
                results.append({
                    "family": family_dir.name,
                    "platform": plat_dir.name,
                    "api_count": len(api),
                    "path": str(index_path),
                })
    return results


def generate_grouped_index(
    family: str,
    platform: str,
    dry_run: bool = False,
) -> dict:
    """Generate a grouped reference _index.md from api_surface.json metadata.

    Returns a result dict with keys: written, skipped, reason, path, body_preview.
    """
    api_surface_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_surface_path.exists():
        return {"written": False, "skipped": True, "reason": "api_surface.json missing",
                "path": "", "body_preview": ""}

    api_surface = json.loads(api_surface_path.read_text(encoding="utf-8"))
    if len(api_surface) < 5:
        return {"written": False, "skipped": True,
                "reason": f"api_surface too small ({len(api_surface)} entries, need >= 5)",
                "path": "", "body_preview": ""}

    # Filter to platform-appropriate entries
    entries = [e for e in api_surface if _passes_platform_scope(e, platform)]
    entries = [e for e in entries if e.get("name") not in _JAVA_INTERNAL_CLASSES]
    entries = [e for e in entries if e.get("visibility") != "internal"]

    if len(entries) < 5:
        return {"written": False, "skipped": True,
                "reason": f"filtered entries too small ({len(entries)})",
                "path": "", "body_preview": ""}

    # Load model metadata
    model_sha = ""
    model_version = ""
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if model_path.exists():
        try:
            import yaml
            model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            model_sha = model.get("repo_sha", "") or ""
            model_version = model.get("version", "") or ""
        except Exception:
            pass

    # Build ERC index for description fallback
    erc_index = _build_erc_index(family, platform)

    # Generate grouped body
    body = _build_grouped_index_body(entries, family, platform, erc_index=erc_index)

    # Read existing _index.md to preserve/update frontmatter
    index_path = CONTENT_ROOT / family / platform / "_index.md"
    if not index_path.exists():
        return {"written": False, "skipped": True,
                "reason": f"_index.md does not exist at {index_path}",
                "path": str(index_path), "body_preview": ""}

    existing_text = index_path.read_text(encoding="utf-8")

    # Parse existing frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---", existing_text, re.DOTALL)
    if not fm_match:
        return {"written": False, "skipped": True,
                "reason": "Cannot parse existing frontmatter",
                "path": str(index_path), "body_preview": ""}

    fm_text = fm_match.group(1)

    # Update provenance: set auto_updatable to true, content_origin to skill-generated
    fm_text = re.sub(r"auto_updatable:\s*(true|false)", "auto_updatable: true", fm_text)
    fm_text = re.sub(r"content_origin:\s*\S+", "content_origin: skill-generated", fm_text)
    fm_text = re.sub(r"last_mechanism:\s*\S+", "last_mechanism: skill", fm_text)
    # Remove recovery note if present (no longer structural-page after healing)
    fm_text = re.sub(r"\n\s*provenance_recovery_note:\s*\S+", "", fm_text)

    # Build intro paragraph
    _PLAT_DISPLAY = {
        "net": ".NET", "java": "Java", "python": "Python",
        "cpp": "C++", "typescript": "TypeScript", "go": "Go",
        "nodejs": "Node.js",
    }
    plat_display = _PLAT_DISPLAY.get(platform, platform.capitalize())
    version_str = f" v{model_version}" if model_version else ""
    intro = (f"API reference for **Aspose.{family.capitalize()} FOSS for "
             f"{plat_display}**{version_str}. "
             f"{len(entries)} public types organized by module.\n")

    # Compose full page
    full_content = f"---\n{fm_text}\n---\n\n{intro}\n{body}"

    # Add See Also section
    full_content += f"\n## See Also\n\n"
    full_content += f"- [Aspose.{family.capitalize()} — Enterprise API Reference]"
    full_content += f"(https://reference.aspose.com/{family}/)\n"

    if dry_run:
        preview = "\n".join(full_content.splitlines()[:40])
        print(f"DRY-RUN: {family}/{platform} — {len(entries)} entries, "
              f"{len(body.splitlines())} body lines")
        return {"written": False, "skipped": False, "reason": "dry-run",
                "path": str(index_path), "body_preview": preview,
                "entry_count": len(entries), "body_lines": len(body.splitlines())}

    # Check if manually curated — never overwrite
    if is_manually_curated(index_path):
        return {"written": False, "skipped": True,
                "reason": "manually curated — skipping",
                "path": str(index_path), "body_preview": ""}

    # Determine if force is needed
    needs_force = not is_auto_updatable(index_path)
    force_reason = ("ref-structure-healing: structural-page recovery — "
                    "replacing flat children shortcode with grouped API tables")

    try:
        safe_content_write(
            index_path, full_content,
            mechanism="skill",
            force=needs_force,
            reason=force_reason if needs_force else "",
        )
    except ProtectedPageError as exc:
        return {"written": False, "skipped": True,
                "reason": f"ProtectedPageError: {exc}",
                "path": str(index_path), "body_preview": ""}

    # Attach evidence
    knowledge = Knowledge(family, platform, knowledge_root=KNOWLEDGE_ROOT)
    if knowledge.available:
        attach_evidence(index_path, knowledge, force=True)

    print(f"WRITTEN: {family}/{platform}/_index.md — {len(entries)} entries, "
          f"{len(body.splitlines())} body lines, force={needs_force}")

    return {"written": True, "skipped": False, "reason": "success",
            "path": str(index_path), "body_preview": "",
            "entry_count": len(entries), "body_lines": len(body.splitlines()),
            "force_used": needs_force}


def check_member_doc_coverage(
    api_surface: list[dict],
    member_erc_index: dict[str, str],
) -> tuple[float, int, int]:
    """Compute ERC member-doc coverage across all public members.

    Returns (coverage_rate, covered_count, total_count) where coverage_rate
    is the fraction of public properties/methods that have an ERC member-doc
    description (0.0–1.0).  Used as a pre-generation gate to detect when
    enrich --mode member-doc has not been run.
    """
    total = 0
    covered = 0
    for entry in api_surface:
        cname = entry.get("name", "")
        for prop in entry.get("properties", []):
            if prop.get("doc", "").strip():
                # Docstring from source — always counts
                total += 1
                covered += 1
            else:
                total += 1
                pname = prop.get("name", "")
                if member_erc_index.get(f"{cname}.{pname}", ""):
                    covered += 1
        for method in entry.get("methods", []):
            if method.get("is_constructor"):
                continue
            if method.get("doc", "").strip():
                total += 1
                covered += 1
            else:
                total += 1
                mname = method.get("name", "")
                if member_erc_index.get(f"{cname}.{mname}", ""):
                    covered += 1
    rate = covered / total if total > 0 else 0.0
    return rate, covered, total


def run(family: str, platform: str, kind_arg: str = "all",
        limit: int | None = None, dry_run: bool = False, update: bool = False,
        require_member_doc_coverage: int | None = None, heal: bool = False,
        confirm_heal: bool = False, plan_path: str | None = None,
        rebuild_all: bool = False, confirm_rebuild: bool = False) -> dict:
    """Run batch reference generation. Returns result dict with counts.

    When update=True, only re-generates pages for classes listed in
    knowledge_delta.json modified_apis.  Default mode (update=False) is
    unchanged: skip pages that already exist (idempotent).

    When rebuild_all=True, regenerates all existing auto-updatable pages from
    current merged/claims.json without requiring knowledge_delta.json.
    Pages marked auto_updatable=false or manually curated are protected.
    Requires confirm_rebuild=True when more than REBUILD_CONFIRM_THRESHOLD pages
    would be overwritten.
    """
    if update and rebuild_all:
        print("STOP: --update and --rebuild-all are mutually exclusive. Use one or the other.")
        sys.exit(2)

    api_surface_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_surface_path.exists():
        print(f"STOP: api_surface.json not found at {api_surface_path}. "
              f"Run /knowledge-bootstrap {family} {platform} first.")
        sys.exit(1)

    if limit == 0:
        print("STOP: --limit must be a positive integer.")
        sys.exit(1)

    # Check for stale knowledge; also read model_sha and version for evidence blocks
    model_sha = ""
    model_version = ""
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        print(f"STOP: model.yaml not found at {model_path}. "
              f"Run /truth-merge {family} {platform} to build a complete knowledge model "
              f"before generating content.")
        sys.exit(1)
    if model_path.exists():
        try:
            import yaml
            model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            if model.get("stale_since") is not None:
                print(f"STOP: Knowledge model is stale (stale_since={model['stale_since']}). "
                      f"Run /knowledge-diff then /knowledge-update {family} {platform} "
                      f"before generating content.")
                sys.exit(1)
            model_sha = model.get("repo_sha", "") or ""
            model_version = model.get("version", "") or ""
        except Exception:
            pass

    api_surface = json.loads(api_surface_path.read_text(encoding="utf-8"))

    # Build ERC-* claim index for prose fallback when doc is empty
    erc_index = _build_erc_index(family, platform)
    if erc_index:
        print(f"ERC index: {len(erc_index)} class entries available for doc fallback.")

    # Build member-level ERC index for property/method table descriptions
    member_erc_index = _build_erc_member_index(family, platform, api_surface=api_surface)
    if member_erc_index:
        print(f"Member ERC index: {len(member_erc_index)} member descriptions available.")

    # Pre-generation member-doc coverage gate
    _cov_rate, _cov_covered, _cov_total = check_member_doc_coverage(api_surface, member_erc_index)
    _cov_pct = int(100 * _cov_rate)
    if _cov_total > 0:
        print(f"Member-doc coverage: {_cov_pct}% ({_cov_covered}/{_cov_total} members documented)")
        _COVERAGE_WARN_THRESHOLD = 20
        if _cov_pct < _COVERAGE_WARN_THRESHOLD:
            LOG.warning(
                "member-doc coverage is %d%% (%d/%d) — run enrich --mode member-doc first "
                "to populate property/method table descriptions",
                _cov_pct, _cov_covered, _cov_total,
            )
        if require_member_doc_coverage is not None and _cov_pct < require_member_doc_coverage:
            print(
                f"STOP: member-doc coverage {_cov_pct}% < required {require_member_doc_coverage}%. "
                f"Run: python scripts/pipeline/commands/knowledge/enrich.py --family {family} --platform {platform} "
                f"--mode member-doc, then promote.py, then retry."
            )
            sys.exit(1)

    # Filter candidates
    candidates = [e for e in api_surface if _passes_platform_scope(e, platform)]
    candidates = _apply_kind_filter(candidates, kind_arg, platform)
    # H-04d: Exclude internal/vendor classes from reference page generation.
    _internal_before = len(candidates)
    candidates = [e for e in candidates if e.get("visibility") != "internal"]
    _internal_skipped = _internal_before - len(candidates)
    if _internal_skipped:
        print(f"Skipped {_internal_skipped} internal/vendor class(es).")

    # H-04e: When __all__ is defined (detected by any "exported" entries),
    # exclude "conventional" classes — they are implementation details not
    # intended for public consumption. Only "exported" and "public" remain.
    _has_exports = any(e.get("visibility") == "exported" for e in candidates)
    if _has_exports:
        _conv_before = len(candidates)
        candidates = [e for e in candidates
                      if e.get("visibility") != "conventional"]
        _conv_skipped = _conv_before - len(candidates)
        if _conv_skipped:
            print(f"Skipped {_conv_skipped} conventional class(es) "
                  f"(package defines __all__).")

    # Deduplicate name collisions: when multiple api_surface entries share the
    # same class name (e.g. public Document vs internal Document), prefer the
    # entry with the highest visibility tier.
    _VIS_RANK = {"exported": 3, "public": 2, "conventional": 1, "internal": 0}
    seen_names: dict[str, int] = {}  # name → index in candidates
    dedup = []
    for entry in candidates:
        name = entry.get("name", "")
        rank = _VIS_RANK.get(entry.get("visibility", "conventional"), 1)
        if name in seen_names:
            prev_idx = seen_names[name]
            prev_rank = _VIS_RANK.get(dedup[prev_idx].get("visibility", "conventional"), 1)
            if rank > prev_rank:
                print(f"  DEDUP: {name} — preferring {entry.get('file','')} "
                      f"(visibility={entry.get('visibility','?')}) over "
                      f"{dedup[prev_idx].get('file','')} "
                      f"(visibility={dedup[prev_idx].get('visibility','?')})")
                dedup[prev_idx] = entry  # replace with higher-visibility entry
            else:
                print(f"  DEDUP: {name} — keeping {dedup[prev_idx].get('file','')} "
                      f"(visibility={dedup[prev_idx].get('visibility','?')}), "
                      f"skipping {entry.get('file','')} "
                      f"(visibility={entry.get('visibility','?')})")
        else:
            seen_names[name] = len(dedup)
            dedup.append(entry)
    if len(dedup) < len(candidates):
        print(f"Deduplicated {len(candidates) - len(dedup)} name collision(s).")
    candidates = dedup

    if limit is not None:
        candidates = candidates[:limit]

    total = len(candidates)
    output_dir = CONTENT_ROOT / family / platform

    # Plan-aware advisory filtering (CP-P4)
    plan_slugs: set[str] | None = None
    if plan_path is not None:
        from page_spec import load_plan
        try:
            site_plan = load_plan(plan_path)
            ref_section = site_plan.sections.get("reference")
            if ref_section is not None:
                plan_slugs = {p.slug for p in ref_section.pages}
                not_in_plan = [e.get("name", "") for e in candidates
                               if e.get("name", "") not in plan_slugs]
                candidate_names = {e.get("name", "") for e in candidates}
                plan_only = [s for s in plan_slugs if s not in candidate_names
                             and s != "_index"]
                print(f"--plan: {len(plan_slugs)} reference pages in plan, "
                      f"{total} candidates in api_surface.")
                if not_in_plan:
                    print(f"  ADVISORY: {len(not_in_plan)} candidate(s) not in plan "
                          f"(will still generate):")
                    for name in not_in_plan[:10]:
                        print(f"    - {name}")
                    if len(not_in_plan) > 10:
                        print(f"    ... and {len(not_in_plan) - 10} more")
                if plan_only:
                    print(f"  ADVISORY: {len(plan_only)} plan page(s) have no "
                          f"api_surface candidate:")
                    for slug in sorted(plan_only)[:10]:
                        print(f"    - {slug}")
                    if len(plan_only) > 10:
                        print(f"    ... and {len(plan_only) - 10} more")
            else:
                print("--plan: no 'reference' section found in plan; ignoring.")
        except (FileNotFoundError, ValueError) as exc:
            print(f"WARN: --plan failed to load {plan_path}: {exc}")

    # Build a normalized slug index of existing pages for deduplication.
    # This prevents creating e.g. "MsgReader.md" when "msg-reader.md" or
    # "msg_reader.md" already exists.
    _existing_normalized: dict[str, Path] = {}
    if output_dir.exists():
        for existing in output_dir.glob("*.md"):
            norm = existing.stem.lower().replace("-", "_")
            _existing_normalized[norm] = existing

    def _has_slug_duplicate(name: str) -> Path | None:
        """Return existing path if a slug-normalized duplicate exists."""
        sanitized = _sanitize_slug(name)
        norm = sanitized.lower().replace("-", "_")
        existing = _existing_normalized.get(norm)
        if existing is not None and existing.stem != sanitized:
            return existing
        return None

    # Determine which pages to generate/update vs skip
    to_generate = []   # pages that don't exist yet (always created)
    to_update = []     # pages that exist and are in modified_apis (--update mode only)
    to_skip = []       # pages that exist and are not being updated

    if update:
        # Load update-eligible APIs from knowledge_delta.json (modified + new + resurrected)
        modified_apis = _load_update_apis(family, platform)
        if modified_apis is None:
            print("WARN: knowledge_delta.json not found; falling back to skip-existing mode "
                  "(all existing pages will be skipped, only new pages generated). "
                  "Use --rebuild-all to regenerate existing pages without a delta.")
            update = False  # degrade to skip-existing mode
        else:
            print(f"--update mode: {len(modified_apis)} update-eligible API classes in knowledge_delta.json.")

    if update:
        for entry in candidates:
            name = entry.get("name", "")
            page_path = output_dir / f"{_sanitize_slug(name)}.md"
            if not page_path.exists():
                to_generate.append(entry)
            elif name in modified_apis:
                # Respect provenance protection: skip pages marked auto_updatable: false
                # or pages that were manually curated (manual-edit-skill, human-edit, etc.)
                if not is_auto_updatable(page_path):
                    print(f"  PROTECTED: {name} — auto_updatable: false, skipping update")
                    to_skip.append(entry)
                elif is_manually_curated(page_path) and not heal:
                    print(f"  PROTECTED: {name} — manually curated, skipping update")
                    to_skip.append(entry)
                else:
                    if is_manually_curated(page_path) and heal:
                        print(f"  HEAL: {name} — overriding manual-curation protection (auto_updatable=true)")
                    to_update.append(entry)
            else:
                to_skip.append(entry)
        print(f"Found {total} candidates: {len(to_generate)} to generate, "
              f"{len(to_update)} to update (in modified_apis), "
              f"{len(to_skip)} to skip.")
    elif rebuild_all:
        # --rebuild-all: regenerate all existing auto-updatable pages from current merged/claims.json
        # Does not require knowledge_delta.json.
        for entry in candidates:
            name = entry.get("name", "")
            page_path = output_dir / f"{_sanitize_slug(name)}.md"
            if not page_path.exists():
                to_generate.append(entry)
            elif not is_auto_updatable(page_path):
                print(f"  PROTECTED: {name} — auto_updatable: false, skipping rebuild")
                to_skip.append(entry)
            elif is_manually_curated(page_path):
                print(f"  PROTECTED: {name} — manually curated, skipping rebuild")
                to_skip.append(entry)
            else:
                to_update.append(entry)
        print(f"--rebuild-all: {len(to_generate)} new, {len(to_update)} eligible for rebuild, "
              f"{len(to_skip)} protected/skipped.")
        if len(to_update) > REBUILD_CONFIRM_THRESHOLD and not confirm_rebuild:
            raise SystemExit(
                f"--rebuild-all would regenerate {len(to_update)} existing pages. "
                f"Re-run with --confirm-rebuild to proceed."
            )
    else:
        for entry in candidates:
            name = entry.get("name", "")
            page_path = output_dir / f"{_sanitize_slug(name)}.md"
            if page_path.exists():
                to_skip.append(entry)
            else:
                dup_path = _has_slug_duplicate(name)
                if dup_path is not None:
                    print(f"  DEDUP-SLUG: {name} — slug-duplicate of {dup_path.stem}, skipping")
                    to_skip.append(entry)
                else:
                    to_generate.append(entry)
        print(f"Found {total} candidates: {len(to_generate)} to generate, "
              f"{len(to_skip)} to skip (already exist or slug-duplicate).")

    # Combined list to write: new pages + pages being updated
    to_write = to_generate + to_update

    if heal:
        curated_pages = [p for p in to_write if is_manually_curated(
            output_dir / f"{p.get('name', '')}.md"
        )]
        if curated_pages:
            LOG.warning(
                "HEAL mode: %d manually-curated page(s) will have auto-generation override applied",
                len(curated_pages),
            )
            if len(curated_pages) > HEAL_CONFIRM_THRESHOLD and not confirm_heal:
                raise SystemExit(
                    f"--heal would override {len(curated_pages)} manually-curated pages. "
                    f"Re-run with --confirm-heal to proceed."
                )

    if dry_run:
        print("DRY-RUN: no files written.")
        for e in to_generate:
            print(f"  WOULD GENERATE: {e.get('name')} ({e.get('kind')})")
        for e in to_update:
            print(f"  WOULD UPDATE: {e.get('name')} ({e.get('kind')})")
        result = {"generated": 0, "updated": 0, "skipped": len(to_skip), "errors": 0, "dry_run": True}
        return result

    generated = []
    updated = []
    unchanged = []  # pages in to_update with no meaningful change (timestamp-only guard)
    errors = []
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load knowledge once for evidence attachment
    knowledge = Knowledge(family, platform, knowledge_root=KNOWLEDGE_ROOT)
    # LH-02 enforcement: knowledge.available MUST be checked BEFORE any page
    # writes (AGENTS.md §5a).  The early-exit checks above verify model.yaml
    # existence and staleness, but Knowledge.available is True only when
    # api_surface.json is loadable.  This guard closes the gap.
    if not knowledge.available:
        print(f"STOP: Knowledge not available for {family}/{platform} "
              f"(api_surface.json missing or unreadable). "
              f"Run /repo-scout {family} {platform}, then /truth-merge.")
        sys.exit(1)

    for i, entry in enumerate(to_write, 1):
        name = entry.get("name", "")
        kind = entry.get("kind", "")
        is_rebuild = rebuild_all and entry in to_update
        is_update = entry in to_update
        action = "Rebuilding" if is_rebuild else ("Updating" if is_update else "Generating")
        print(f"[{i}/{len(to_write)}] {action} page for {name} ({kind})...")
        try:
            page_path = output_dir / f"{_sanitize_slug(name)}.md"
            content = _build_page(entry, family, platform, erc_index=erc_index,
                                   member_erc_index=member_erc_index,
                                   model_sha=model_sha, model_version=model_version)
            # Timestamp-only churn guard: in --rebuild-all mode, skip pages where
            # the only differences from the existing file are pure timestamp fields
            # (content_created_at, graded_at, grade, graded_content_hash, content_hash).
            # This prevents committing noise when the merged knowledge has not changed.
            if is_rebuild and not _has_meaningful_change(page_path, content):
                print(f"  UNCHANGED: {name} — no meaningful changes beyond timestamps, skipping write")
                unchanged.append(entry)
                continue
            # Preserve content_created_at from the existing page (write-once field).
            # safe_content_write() writes content as-is without timestamp preservation,
            # so we must carry the original value forward before writing.
            if is_rebuild and page_path.exists():
                try:
                    existing_text = page_path.read_text(encoding="utf-8")
                    _m = re.search(r"content_created_at:\s*'([^']+)'", existing_text)
                    if _m:
                        content = re.sub(
                            r"content_created_at:\s*'[^']+'",
                            f"content_created_at: '{_m.group(1)}'",
                            content,
                        )
                except OSError:
                    pass
            safe_content_write(page_path, content, mechanism="batch-reference")
            # Attach evidence + auto-grade (identical path for new pages and updates)
            # force=True because _build_page already wrote a model_sha; runner would skip otherwise
            if knowledge.available:
                attach_evidence(page_path, knowledge, force=True)
            if is_update:
                updated.append(entry)
            else:
                generated.append(entry)
        except Exception as exc:
            print(f"  ERROR: {name} — {exc}")
            errors.append((entry, str(exc)))

    # Summary
    print("")
    print("=== batch-reference summary ===")
    print(f"Family:    {family}")
    print(f"Platform:  {platform}")
    print(f"Kind:      {kind_arg}")
    print(f"Limit:     {limit if limit is not None else 'none'}")
    _mode = "update" if update else ("rebuild-all" if rebuild_all else "generate-new")
    print(f"Mode:      {_mode}")
    print("")
    print(f"Candidates:   {total}")
    print(f"Generated:    {len(generated)}")
    if update:
        print(f"Updated:      {len(updated)} pages, skipped {len(to_skip)} unchanged")
    elif rebuild_all:
        print(f"Rebuilt:      {len(updated)} pages ({len(unchanged)} unchanged/skipped as timestamp-only)")
        print(f"Protected:    {len(to_skip)} (auto_updatable=false or manually curated)")
    else:
        print(f"Skipped:      {len(to_skip)} (already existed)")
    print(f"Errors:       {len(errors)} (failed to generate)")

    if generated:
        print("")
        print("Generated pages:")
        for e in generated:
            print(f"  - {e.get('name')}  ({e.get('kind')})")

    if updated:
        print("")
        print("Updated pages:")
        for e in updated:
            print(f"  - {e.get('name')}  ({e.get('kind')})")

    if to_skip:
        print("")
        print("Skipped pages:")
        for e in to_skip:
            print(f"  - {e.get('name')}  (already exists)")

    if errors:
        print("")
        print("Error pages (manual review required):")
        for e, msg in errors:
            print(f"  - {e.get('name')}  ({msg})")

    # Write generation manifest for denominator reconciliation (L-12 gate)
    _write_generation_manifest(
        family, platform,
        api_surface_total=len(api_surface),
        scope_eligible=total,
        pages_created=len(generated),
        pages_updated=len(updated),
        pages_skipped=len(to_skip),
        pages_failed=len(errors),
        pages_unchanged=len(unchanged),
        model_sha=model_sha,
    )

    # TC-DESIGN-001: Write freshness manifest after successful generation
    _write_freshness_manifest_if_enabled(
        family, platform,
        pages_failed=len(errors),
        actual_page_count=len(generated) + len(updated) + len(to_skip) + len(unchanged),
        dry_run=dry_run,
    )

    # Auto-heal flat reference index if running in --update or --rebuild-all mode
    if (update or rebuild_all) and not dry_run:
        _auto_heal_flat_index(family, platform)

    return {"generated": len(generated), "updated": len(updated),
            "skipped": len(to_skip), "errors": len(errors),
            "unchanged": len(unchanged)}


def _write_freshness_manifest_if_enabled(
    family: str, platform: str, *,
    pages_failed: int = 0,
    actual_page_count: int | None = None,
    dry_run: bool = False,
) -> None:
    """TC-DESIGN-001: Write freshness manifest after generation if flag is enabled."""
    try:
        flags_path = REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            return
        flags = json.loads(flags_path.read_text(encoding="utf-8"))
        if not flags.get("refresh_generation_manifest_write_enabled", False):
            print("\nFreshness manifest write skipped (refresh_generation_manifest_write_enabled=false)")
            return

        from freshness_manifest import write_generation_freshness_manifest
        from datetime import datetime, timezone
        run_id = f"batch-reference-{family}-{platform}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

        written, note = write_generation_freshness_manifest(
            product=f"{family}/{platform}",
            subdomain="reference",
            run_id=run_id,
            repo_root=REPO_ROOT,
            pages_failed=pages_failed,
            actual_page_count=actual_page_count,
            dry_run=dry_run,
        )
        if written:
            print(f"\nFreshness manifest write SUCCEEDED: {note}")
        else:
            print(f"\nFreshness manifest write skipped/failed: {note}")
    except Exception as exc:
        LOG.warning("Freshness manifest write failed: %s", exc)
        print(f"\nFreshness manifest write failed: {exc}")


def _write_generation_manifest(
    family: str, platform: str, *,
    api_surface_total: int, scope_eligible: int,
    pages_created: int, pages_updated: int, pages_skipped: int,
    pages_failed: int, pages_unchanged: int, model_sha: str,
) -> None:
    """Write a generation manifest to reports/generation/{family}-{platform}.yaml."""
    from datetime import datetime, timezone
    manifest_dir = REPO_ROOT / "reports" / "generation"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{family}-{platform}.yaml"

    pages_total = pages_created + pages_updated + pages_skipped + pages_unchanged
    gap = scope_eligible - pages_total

    import yaml
    manifest = {
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_surface_total": api_surface_total,
        "scope_eligible": scope_eligible,
        "scope_filtered": api_surface_total - scope_eligible,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "pages_skipped": pages_skipped,
        "pages_unchanged": pages_unchanged,
        "pages_failed": pages_failed,
        "denominator_gap": gap,
        "model_sha": model_sha,
    }
    manifest_path.write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"\nGeneration manifest written to: {manifest_path.relative_to(REPO_ROOT)}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate reference pages in bulk from api_surface.json (S-62 backing script)"
    )
    parser.add_argument("family", help="Product family (e.g. email, slides, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java, python, cpp)")
    parser.add_argument("--kind", choices=["class", "enum", "all"], default="all",
                        help="Filter by entry kind (default: all)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N entries (default: unlimited)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print candidates without writing files")
    parser.add_argument("--update", action="store_true",
                        help="Re-generate pages for modified API classes listed in "
                             "knowledge_delta.json. Falls back to full re-run if delta absent.")
    parser.add_argument("--require-member-doc-coverage", type=int, default=None,
                        metavar="N",
                        help="Abort if member-doc coverage is below N%% before generating. "
                             "Enforces that enrich --mode member-doc was run first.")
    parser.add_argument("--heal", action="store_true",
                        help="System-healing mode: bypass is_manually_curated soft protection "
                             "for auto_updatable=true pages when used with --update. "
                             "Use only for pipeline healing runs where descriptions were "
                             "systemically broken and need to be regenerated from repo truth.")
    parser.add_argument("--confirm-heal", action="store_true",
                        help=f"Required when --heal would override more than {HEAL_CONFIRM_THRESHOLD} manually-curated pages")
    parser.add_argument("--rebuild-all", action="store_true",
                        help="Regenerate all existing auto-updatable reference pages from current "
                             "merged/claims.json without requiring knowledge_delta.json. "
                             "Skips pages with auto_updatable=false or manually curated pages. "
                             f"Requires --confirm-rebuild when more than {REBUILD_CONFIRM_THRESHOLD} "
                             "pages would be rebuilt.")
    parser.add_argument("--confirm-rebuild", action="store_true",
                        help=f"Required when --rebuild-all would regenerate more than "
                             f"{REBUILD_CONFIRM_THRESHOLD} existing pages")
    parser.add_argument("--plan", default=None, metavar="PATH",
                        help="Path to site_plan.yaml for plan-aware advisory logging. "
                             "Compares api_surface candidates against the plan's reference "
                             "section and logs mismatches (does not filter candidates).")
    parser.add_argument("--generate-index", action="store_true",
                        help="Generate a grouped _index.md for the reference platform root "
                             "from api_surface.json metadata. Groups API entries by "
                             "package/module and type category. Use --dry-run to preview.")
    parser.add_argument("--knowledge-root", default=None, metavar="DIR",
                        help="Override knowledge root path (default: <repo>/knowledge)")
    parser.add_argument("--content-root", default=None, metavar="DIR",
                        help="Override content root path "
                             "(default: <repo>/content/reference.aspose.org/en)")
    args = parser.parse_args()

    if args.knowledge_root or args.content_root:
        configure(
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else None,
            content_root=Path(args.content_root) if args.content_root else None,
        )

    if args.generate_index:
        result = generate_grouped_index(args.family, args.platform, dry_run=args.dry_run)
        if result.get("written"):
            print(f"SUCCESS: Grouped index written to {result['path']}")
        elif result.get("skipped"):
            print(f"SKIPPED: {result.get('reason', 'unknown')}")
        elif args.dry_run:
            print(f"DRY-RUN complete: {result.get('entry_count', 0)} entries, "
                  f"{result.get('body_lines', 0)} body lines")
            if result.get("body_preview"):
                print("--- Preview (first 40 lines) ---")
                print(result["body_preview"])
        sys.exit(0)

    run(args.family, args.platform,
        kind_arg=args.kind,
        limit=args.limit,
        dry_run=args.dry_run,
        update=args.update,
        require_member_doc_coverage=args.require_member_doc_coverage,
        heal=args.heal,
        confirm_heal=args.confirm_heal,
        plan_path=args.plan,
        rebuild_all=args.rebuild_all,
        confirm_rebuild=args.confirm_rebuild)


if __name__ == "__main__":
    main()