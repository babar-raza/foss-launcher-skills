"""core/knowledge.py — Re-export shim for the knowledge model.

The canonical implementation lives in ``knowledge_core.py`` (sibling module).
This module re-exports all public symbols so that code can import from either
``knowledge_core`` or ``core.knowledge`` interchangeably.

Note on dependency direction
----------------------------
``knowledge_core.py`` imports ``Finding`` from ``token_ops``, which means it
cannot be in the "zero upstream deps" tier. The re-export approach used here
lets ``core/knowledge.py`` exist as the public API while the implementation
stays in ``knowledge_core.py`` where it can freely import siblings.

Usage::

    # Either of these works:
    from knowledge_core import Knowledge, discover_content
    from core.knowledge import Knowledge, discover_content
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard: core/ sub-package needs pipeline root for knowledge_core.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_core import (  # noqa: E402
    KNOWLEDGE_ROOT,
    PLATFORM_MAP,
    PLATFORM_RMAP,
    SITE_PATHS,
    LOCALE_RE,
    _FRONTMATTER_RE,
    Knowledge,
    discover_content,
    discover_products,
    infer_product,
    parse_frontmatter,
    verify_evidence,
)

__all__ = [
    "KNOWLEDGE_ROOT",
    "PLATFORM_MAP",
    "PLATFORM_RMAP",
    "SITE_PATHS",
    "LOCALE_RE",
    "_FRONTMATTER_RE",
    "Knowledge",
    "discover_content",
    "discover_products",
    "infer_product",
    "parse_frontmatter",
    "verify_evidence",
]
