"""evidence/ — Evidence attachment package.

Extracted from attach_evidence.py (Phase 5). Each sub-module handles one
responsibility:
- sections.py: split markdown body into heading-delimited sections
- mapper.py: format detection + token-to-evidence mapping
- writer.py: write evidence block into frontmatter atomically
- runner.py: orchestration (attach_evidence, attach_product, main)

Backward compat: attach_evidence.py re-exports all symbols from this
package so existing `from attach_evidence import X` call sites still work.
"""
from .sections import (
    _HEADING_RE,
    _CODE_FENCE_RE,
    _parse_sections,
)
from .mapper import (
    _INTERNAL_FORMAT_NAMES,
    _MAX_EXT_LEN,
    _load_known_formats,
    _detect_formats,
    _detect_formats_in_text,
    _map_tokens_to_evidence,
    _extract_section_tokens,
    _section_has_code_blocks,
    _build_sections_evidence,
)
from .writer import (
    _FRONTMATTER_RE,
    _write_evidence_to_frontmatter,
)
from .runner import (
    attach_evidence,
    attach_product,
    attach_files,
    _auto_refresh,
    main,
)

__all__ = [
    "_HEADING_RE",
    "_CODE_FENCE_RE",
    "_parse_sections",
    "_INTERNAL_FORMAT_NAMES",
    "_MAX_EXT_LEN",
    "_load_known_formats",
    "_detect_formats",
    "_detect_formats_in_text",
    "_map_tokens_to_evidence",
    "_extract_section_tokens",
    "_section_has_code_blocks",
    "_build_sections_evidence",
    "_FRONTMATTER_RE",
    "_write_evidence_to_frontmatter",
    "attach_evidence",
    "attach_product",
    "attach_files",
    "_auto_refresh",
    "main",
]
