"""Markdown utilities - frontmatter parsing/writing.

Ported from aspose.org scripts/pipeline/core/markdown.py.
"""
import re
from typing import Dict, Any, Optional, Tuple


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def split_frontmatter(text: str) -> Tuple[Optional[str], str]:
    """Split markdown text into (frontmatter_block, body). Returns (None, text) if no frontmatter."""
    m = FRONTMATTER_RE.match(text)
    if m:
        return m.group(1), text[m.end():]
    return None, text


def has_frontmatter(text: str) -> bool:
    """Return True if text starts with YAML frontmatter."""
    return bool(FRONTMATTER_RE.match(text))
