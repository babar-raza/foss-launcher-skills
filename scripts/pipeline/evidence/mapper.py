"""mapper.py — Token-to-evidence mapping and format detection.

Extracted from attach_evidence.py (Phase 5). Maps API tokens to claim_ids
and api_refs, detects format references in content, and builds per-section
evidence breakdowns.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from content_discovery import KNOWLEDGE_ROOT as _DEFAULT_KNOWLEDGE_ROOT  # noqa: E402  (R-4: was knowledge_core)
from token_ops import (  # noqa: E402
    PLATFORM_SDK_CLASSES,
    PROPERTY_CHAIN_CLASSES,
    extract_tokens,
)
from evidence.sections import _parse_sections  # noqa: E402

# Module-level knowledge root, overridable via configure() for testing
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT


def configure(knowledge_root=None) -> None:
    """Override module-level singletons for testing.

    Call configure() in test setUp/teardown to inject fake dependencies
    without patching guarded path constants directly (T1 compliance).

    Args:
        knowledge_root: Override for KNOWLEDGE_ROOT. Pass None to reset to default.
    """
    global KNOWLEDGE_ROOT  # noqa: PLW0603
    KNOWLEDGE_ROOT = knowledge_root if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT


# Internal implementation class names extracted by scout that are not user-facing formats.
# These appear in formats.json as exporter base/registry/factory classes and must be excluded.
_INTERNAL_FORMAT_NAMES = frozenset({"base", "registry", "factory", "pptxfactory"})

# CV2-003b: Format names that appear in formats.json but are not real file extensions.
# These are internal class/concept names (CFB structure elements, spreadsheet concepts,
# enum constants for non-I/O purposes) that the format extractor picks up from source code.
_FALSE_POSITIVE_EXTS = frozenset({
    # Spreadsheet structural concepts (cells/python)
    "col", "row", "main", "elem",
    # OPC/package concepts (slides/cpp)
    "package",
    # CFB/MSG structure elements (email/python)
    "storage", "value", "address", "flags", "reserved", "clsid", "difat",
    # Slide rendering internals (slides/python)
    "double", "black", "el",
    # Font library internals (font/python)
    "font", "binary", "bit", "slice", "pos", "format",
    # 3D scene internals (3d/python)
    "geometry", "mesh", "material", "rotation", "matrix",
    # Generic false positives
    "argb", "remove", "parts", "i",
})

# Maximum length for a plausible file extension (e.g. "docx"=4, "pptx"=4, "html"=4, "jpeg"=4)
_MAX_EXT_LEN = 8


def _load_known_formats(knowledge) -> list:
    """Load and normalise known formats from formats.json.

    FIX-06: Only include formats with direction: export or import.
    Formats with direction: detect are enum-only entries (SaveFormat
    constant exists but no backing I/O class) and must not appear in
    evidence as supported formats.
    """
    formats_path = (KNOWLEDGE_ROOT / knowledge.family / knowledge.platform
                    / "merged" / "formats.json")
    if not formats_path.exists():
        return []

    known_formats = json.loads(formats_path.read_text(encoding="utf-8"))
    if not isinstance(known_formats, list):
        return []

    result = []
    for entry in known_formats:
        if not isinstance(entry, dict):
            continue
        ext = entry.get("extension", entry.get("ext", entry.get("format", ""))).lower().lstrip(".")
        if not ext or ext in _INTERNAL_FORMAT_NAMES or ext in _FALSE_POSITIVE_EXTS or len(ext) > _MAX_EXT_LEN:
            continue
        support = entry.get("support", entry.get("direction", ""))
        # FIX-06: skip detect-only formats — they have no backing I/O class
        if support in ("detect", "enum_only"):
            continue
        # FIX-13: skip formats marked as non-functional (enum exists but
        # I/O implementation throws or is absent)
        if entry.get("functional") is False:
            continue
        result.append({"ext": ext, "support": support})
    return result


def _detect_formats(filepath, knowledge) -> list:
    """Scan page body for format extension mentions; cross-ref against formats.json."""
    known = _load_known_formats(knowledge)
    if not known:
        return []

    text = filepath.read_text(encoding="utf-8").lower()
    result = []
    seen_exts = set()
    for entry in known:
        ext = entry["ext"]
        if ext in seen_exts:
            continue
        if re.search(rf'\.{re.escape(ext)}\b|(?<![a-z]){re.escape(ext)}(?![a-z])', text):
            result.append(entry)
            seen_exts.add(ext)
    return result


def _detect_formats_in_text(text, knowledge) -> list:
    """Detect format references within a text string (for per-section detection)."""
    known = _load_known_formats(knowledge)
    if not known:
        return []

    text_lower = text.lower()
    result = []
    seen_exts = set()
    for entry in known:
        ext = entry["ext"]
        if ext in seen_exts:
            continue
        if re.search(rf'\.{re.escape(ext)}\b|(?<![a-z]){re.escape(ext)}(?![a-z])', text_lower):
            result.append(entry)
            seen_exts.add(ext)
    return result


def _map_tokens_to_evidence(tokens, knowledge) -> tuple[list, list]:
    """Map a list of tokens to claim_ids and api_refs.

    Returns (claim_ids: list[str], api_refs: list[str]).
    """
    claim_ids = []
    api_refs = []
    seen_refs = set()

    for tok in tokens:
        if tok.kind in ("import", "table_member"):
            continue
        cls = tok.class_name
        if not cls or cls not in knowledge.classes:
            continue
        if cls in PLATFORM_SDK_CLASSES or cls in PROPERTY_CHAIN_CLASSES:
            continue
        member = tok.member_name if tok.member_name and tok.member_name != "__init__" else None
        if member and not knowledge.has_method(cls, member) \
                and not knowledge.has_property(cls, member) \
                and not knowledge.has_enum_member(cls, member):
            member = None

        ref = f"{cls}.{member}" if member else cls
        if ref in seen_refs:
            continue
        seen_refs.add(ref)

        # Use ClassName.method for method calls; fall back to ClassName-only for
        # constructors (__init__) so ERC- class-level claim keys can be resolved.
        raw_member = tok.member_name
        if raw_member and raw_member != "__init__":
            api_key = f"{cls}.{raw_member}"
        else:
            api_key = cls
        cid = knowledge.api_to_claim.get(api_key)
        if not cid and raw_member and raw_member != "__init__":
            # Also try class-only fallback for ERC- resolution when method key misses
            cid = knowledge.api_to_claim.get(cls)
        if cid:
            claim_ids.append(cid)
        if member:
            api_refs.append(f"{cls}.{member}")

    return claim_ids, api_refs


def _load_delta_modified_apis(knowledge) -> set:
    """Load the set of modified API names from knowledge_delta.json.

    Returns an empty set if the delta file does not exist or has no modified_apis.
    """
    delta_path = (KNOWLEDGE_ROOT / knowledge.family / knowledge.platform
                  / "merged" / "knowledge_delta.json")
    if not delta_path.exists():
        return set()
    try:
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return set(delta.get("modified_apis", []))


def _api_name_fallback_match(filepath, knowledge, already_matched: set) -> tuple[list, list]:
    """Fallback: scan page body prose for modified API names not captured by token extraction.

    Reads knowledge_delta.json for modified_apis and searches the page body text (outside
    code blocks) for word-boundary occurrences of those API names. Only adds matches for
    APIs that (a) exist in the current knowledge model, (b) are in the modified_apis list,
    and (c) were not already captured by code-block token extraction.

    Args:
        filepath: Path to the content file.
        knowledge: Knowledge model instance.
        already_matched: Set of ref strings (e.g. "ClassName" or "ClassName.member")
            already captured by _map_tokens_to_evidence — avoids double-counting.

    Returns (claim_ids: list[str], api_refs: list[str]).
    """
    modified_apis = _load_delta_modified_apis(knowledge)
    if not modified_apis:
        return [], []

    # Read page content; strip YAML frontmatter before scanning
    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError:
        return [], []

    if text.startswith("---"):
        end_fm = text.find("\n---", 3)
        if end_fm != -1:
            text = text[end_fm + 4:]

    # Remove fenced code blocks to limit matches to prose text only.
    # This prevents re-matching APIs already captured by token extraction.
    text_prose = re.sub(r"```[\s\S]*?```", " ", text)

    claim_ids = []
    api_refs = []
    seen = set()

    for api_name in sorted(modified_apis):  # sorted for determinism
        if api_name in seen:
            continue
        if api_name not in knowledge.classes:
            continue
        if api_name in already_matched:
            continue
        if not re.search(rf"\b{re.escape(api_name)}\b", text_prose):
            continue
        cid = knowledge.api_to_claim.get(api_name)
        if not cid:
            continue
        seen.add(api_name)
        claim_ids.append(cid)
        api_refs.append(api_name)

    return claim_ids, api_refs


def _extract_section_tokens(filepath, section, platform) -> list:
    """Extract API tokens from a single section's code blocks."""
    all_tokens = extract_tokens(filepath, platform)

    code_ranges = section["code_ranges"]
    if not code_ranges:
        return []

    section_tokens = []
    for tok in all_tokens:
        for start, end in code_ranges:
            if start <= tok.line_no <= end:
                section_tokens.append(tok)
                break

    return section_tokens


def _section_has_code_blocks(section) -> bool:
    """Return True if section contains at least one code block."""
    return len(section["code_ranges"]) > 0


def _build_sections_evidence(filepath, knowledge) -> list:
    """Build the sections array for paragraph-level evidence.

    Returns a list of section evidence dicts (only sections with evidence).
    """
    sections = _parse_sections(filepath)
    platform = knowledge.platform
    result = []

    # FIX-06: headings that indicate limitation context — format mentions
    # under these headings should not be treated as supported-format evidence.
    _LIMITATION_HEADINGS = frozenset({
        "limitations", "known limitations", "not supported",
        "unsupported", "unsupported formats", "known issues",
        "restrictions", "format limitations",
    })

    for section in sections:
        section_tokens = _extract_section_tokens(filepath, section, platform)
        claim_ids, api_refs = _map_tokens_to_evidence(section_tokens, knowledge)

        section_text = "\n".join(text for _, text in section["body_lines"])
        formats = _detect_formats_in_text(section_text, knowledge)

        # FIX-06: if the section heading is a limitations context, strip
        # format entries — mentioning a format in limitations doesn't mean
        # the product supports it.
        heading_lower = section.get("heading", "").lower().strip()
        if heading_lower in _LIMITATION_HEADINGS:
            formats = []

        # Skip sections with no evidence
        if not claim_ids and not api_refs and not formats:
            continue

        entry = {
            "heading": section["heading"],
            "line": section["line"],
            "claims": sorted(set(claim_ids)),
            "apis": sorted(set(api_refs)),
        }
        if formats:
            entry["formats"] = formats

        result.append(entry)

    return result