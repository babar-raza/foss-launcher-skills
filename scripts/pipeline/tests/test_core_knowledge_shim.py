"""P1 hardening — direct coverage for scripts/pipeline/core/knowledge.py shim.

core/knowledge.py is a backward-compat re-export shim that re-exports symbols
from knowledge_core, content_discovery, evidence_verifier, and core.markdown so
that callers can import from either `knowledge_core` / canonical modules or from
`core.knowledge` interchangeably.

No test previously imported through `core.knowledge` directly. A latent shim bug
survived multiple prior sprints because it was only caught as a side effect of a
full-suite run. These tests close that blind spot.

Exported surface (12 symbols, post R-4):
  From knowledge_core:       Knowledge
  From content_discovery:    KNOWLEDGE_ROOT, PLATFORM_MAP, PLATFORM_RMAP,
                             SITE_PATHS, LOCALE_RE,
                             discover_content, discover_products, infer_product
  From evidence_verifier:    verify_evidence
  From core.markdown:        _FRONTMATTER_RE, parse_frontmatter
"""
from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import core.knowledge as shim  # noqa: E402


# ---------------------------------------------------------------------------
# Section 1 — Full surface importable in one shot
# ---------------------------------------------------------------------------

def test_full_shim_surface_import():
    """All 12 symbols importable from core.knowledge in one import statement."""
    from core.knowledge import (
        Knowledge,
        KNOWLEDGE_ROOT,
        PLATFORM_MAP,
        PLATFORM_RMAP,
        SITE_PATHS,
        LOCALE_RE,
        discover_content,
        discover_products,
        infer_product,
        verify_evidence,
        _FRONTMATTER_RE,
        parse_frontmatter,
    )
    assert callable(Knowledge)
    assert callable(discover_content)
    assert callable(discover_products)
    assert callable(infer_product)
    assert callable(verify_evidence)
    assert callable(parse_frontmatter)
    assert isinstance(KNOWLEDGE_ROOT, Path)
    assert isinstance(PLATFORM_MAP, dict)
    assert isinstance(PLATFORM_RMAP, dict)
    assert isinstance(SITE_PATHS, list)
    assert _FRONTMATTER_RE is not None
    assert LOCALE_RE is not None


# ---------------------------------------------------------------------------
# Section 2 — Symbol identity: shim exports must be the same objects as canonical
# ---------------------------------------------------------------------------

def test_knowledge_is_canonical():
    from core.knowledge import Knowledge
    from knowledge_core import Knowledge as _K
    assert Knowledge is _K


def test_knowledge_root_is_canonical():
    from core.knowledge import KNOWLEDGE_ROOT
    from content_discovery import KNOWLEDGE_ROOT as _KR
    assert KNOWLEDGE_ROOT is _KR


def test_platform_map_is_canonical():
    from core.knowledge import PLATFORM_MAP
    from content_discovery import PLATFORM_MAP as _PM
    assert PLATFORM_MAP is _PM


def test_platform_rmap_is_canonical():
    from core.knowledge import PLATFORM_RMAP
    from content_discovery import PLATFORM_RMAP as _PRM
    assert PLATFORM_RMAP is _PRM


def test_site_paths_is_canonical():
    from core.knowledge import SITE_PATHS
    from content_discovery import SITE_PATHS as _SP
    assert SITE_PATHS is _SP


def test_locale_re_is_canonical():
    from core.knowledge import LOCALE_RE
    from content_discovery import LOCALE_RE as _LR
    assert LOCALE_RE is _LR


def test_discover_content_is_canonical():
    from core.knowledge import discover_content
    from content_discovery import discover_content as _dc
    assert discover_content is _dc


def test_discover_products_is_canonical():
    from core.knowledge import discover_products
    from content_discovery import discover_products as _dp
    assert discover_products is _dp


def test_infer_product_is_canonical():
    from core.knowledge import infer_product
    from content_discovery import infer_product as _ip
    assert infer_product is _ip


def test_verify_evidence_is_canonical():
    from core.knowledge import verify_evidence
    from evidence_verifier import verify_evidence as _ve
    assert verify_evidence is _ve


def test_frontmatter_re_is_canonical():
    from core.knowledge import _FRONTMATTER_RE
    from core.markdown import _FRONTMATTER_RE as _fre
    assert _FRONTMATTER_RE is _fre


def test_parse_frontmatter_is_canonical():
    from core.knowledge import parse_frontmatter
    from core.markdown import parse_frontmatter as _pf
    assert parse_frontmatter is _pf


# ---------------------------------------------------------------------------
# Section 3 — Shim isolation
# ---------------------------------------------------------------------------

def test_private_knowledge_root_does_not_leak_through_shim():
    """_KNOWLEDGE_ROOT is a private alias in knowledge_core and must not appear in shim."""
    assert not hasattr(shim, "_KNOWLEDGE_ROOT"), (
        "_KNOWLEDGE_ROOT is private to knowledge_core and must not be re-exported by core.knowledge"
    )


def test_all_declared_symbols_importable():
    """Regression canary: every symbol in __all__ must import without error.

    If any canonical module moves a symbol, this test breaks before production code breaks.
    """
    import importlib
    for name in shim.__all__:
        obj = getattr(shim, name, None)
        assert obj is not None, (
            f"core.knowledge.__all__ declares '{name}' but it is not accessible as an attribute"
        )
