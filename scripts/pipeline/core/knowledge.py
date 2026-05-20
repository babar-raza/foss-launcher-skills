# Adapted from aspose.org
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

    # Canonical imports (post R-1b / R-3b):
    from knowledge_core import Knowledge          # loader
    from content_discovery import discover_content, discover_products, infer_product
    from evidence_verifier import verify_evidence
    from core.markdown import parse_frontmatter

    # Or via this shim (re-exports all of the above):
    from core.knowledge import Knowledge, discover_content, verify_evidence
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard: core/ sub-package needs pipeline root for knowledge_core.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from knowledge_core import Knowledge  # noqa: E402
from content_discovery import (  # noqa: E402  (R-1b/R-4: was knowledge_core)
    KNOWLEDGE_ROOT,
    PLATFORM_MAP,
    PLATFORM_RMAP,
    SITE_PATHS,
    LOCALE_RE,
    discover_content,
    discover_products,
    infer_product,
)
from evidence_verifier import verify_evidence  # noqa: E402  (R-3b: was knowledge_core)
from core.markdown import (  # noqa: E402
    _FRONTMATTER_RE,  # R-0b: bypass knowledge_core alias
    parse_frontmatter,  # R-2b: was knowledge_core
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