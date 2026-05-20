# Adapted from aspose.org
"""core/markdown.py — Canonical markdown parsing utilities.

Defines the two FRONTMATTER regex variants and parse_frontmatter().
Having both defined here prevents the "3-group vs 1-group" confusion
that existed when each module defined its own copy.

Variants
--------
_FRONTMATTER_READER_RE : re.Pattern
    1-group pattern — extracts the raw YAML body between ``---`` fences.
    Use when you only need to READ the frontmatter content.

_FRONTMATTER_WRITER_RE : re.Pattern
    3-group pattern — splits into (opening fence, YAML body, closing fence).
    Use when you need to REPLACE the frontmatter block in-place.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# 1-group: captures only the YAML body (for reading).
_FRONTMATTER_READER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)

# 3-group: captures (opening-fence, body, closing-fence) (for writing).
_FRONTMATTER_WRITER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)

# Convenience alias — matches the name used in knowledge_core.py callers
_FRONTMATTER_RE = _FRONTMATTER_READER_RE

# Section heading and code fence patterns
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.DOTALL | re.MULTILINE)

# Legacy alias for backward compatibility with older foss code
FRONTMATTER_RE = _FRONTMATTER_READER_RE


def extract_frontmatter_body(text: str) -> str | None:
    """Return the raw YAML body between --- fences, or None if absent."""
    m = _FRONTMATTER_READER_RE.match(text)
    return m.group(1) if m else None


def split_frontmatter(text: str) -> tuple[str, str, str] | None:
    """Split text into (opening_fence, yaml_body, closing_fence) or None."""
    m = _FRONTMATTER_WRITER_RE.match(text)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def has_frontmatter(text: str) -> bool:
    """Return True if text starts with YAML frontmatter."""
    return bool(_FRONTMATTER_READER_RE.match(text))


def parse_frontmatter(filepath: Path) -> dict[str, Any]:
    """Extract YAML frontmatter dict from a markdown file.

    Returns an empty dict if the file has no frontmatter or the YAML is
    malformed.
    """
    text = filepath.read_text(encoding="utf-8")
    m = _FRONTMATTER_READER_RE.match(text)
    if not m:
        return {}
    if yaml is None:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
