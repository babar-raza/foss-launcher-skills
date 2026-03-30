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

from knowledge_core import KNOWLEDGE_ROOT  # noqa: E402
from token_ops import (  # noqa: E402
    PLATFORM_SDK_CLASSES,
    PROPERTY_CHAIN_CLASSES,
    extract_tokens,
)
from evidence.sections import _parse_sections  # noqa: E402


# Internal implementation class names extracted by scout that are not user-facing formats.
# These appear in formats.json as exporter base/registry/factory classes and must be excluded.
_INTERNAL_FORMAT_NAMES = frozenset({"base", "registry", "factory", "pptxfactory"})

# Maximum length for a plausible file extension (e.g. "docx"=4, "pptx"=4, "html"=4, "jpeg"=4)
_MAX_EXT_LEN = 8


def _load_known_formats(knowledge) -> list:
    """Load and normalise known formats from formats.json."""
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
        if not ext or ext in _INTERNAL_FORMAT_NAMES or len(ext) > _MAX_EXT_LEN:
            continue
        support = entry.get("support", entry.get("direction", ""))
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

    for section in sections:
        section_tokens = _extract_section_tokens(filepath, section, platform)
        claim_ids, api_refs = _map_tokens_to_evidence(section_tokens, knowledge)

        section_text = "\n".join(text for _, text in section["body_lines"])
        formats = _detect_formats_in_text(section_text, knowledge)

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
