"""R-0c baseline test — knowledge_core.py public API surface.

This test asserts that all known public symbols can be imported from
knowledge_core.py. It serves as a canary: if any symbol is accidentally
removed during Phase R extractions, this test fails before consumers break.

Current surface (2 symbols, post R-4):
  Knowledge, diff

Removed symbols (see canonical homes):
  discover_content / discover_products / infer_product → content_discovery (R-1b)
  KNOWLEDGE_ROOT / PLATFORM_MAP / PLATFORM_RMAP        → content_discovery (R-4)
  SITE_PATHS / LOCALE_RE                               → content_discovery (R-4)
  verify_evidence                                       → evidence_verifier (R-3b)
  parse_frontmatter / _FRONTMATTER_RE                  → core.markdown (R-2b)

IMPORTANT: Do NOT update this test without also updating the census table in
PIPELINE.md and the migration sprint that removes/moves the symbol.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Import-level smoke test — 2 retained symbols (post R-4)
# ---------------------------------------------------------------------------

def test_knowledge_class_importable():
    from knowledge_core import Knowledge
    assert callable(Knowledge)


def test_diff_importable():
    """diff() is a CLI helper used by tests only. Must remain in knowledge_core."""
    from knowledge_core import diff
    assert callable(diff)


# ---------------------------------------------------------------------------
# Bulk import — complete surface in one shot
# ---------------------------------------------------------------------------

def test_full_api_surface_import():
    """All 2 remaining symbols importable (post R-4).

    Removed from surface (R-1b): discover_content, discover_products, infer_product.
    Removed from surface (R-3b): verify_evidence.
    Removed from surface (R-2b): parse_frontmatter, _FRONTMATTER_RE.
    Removed from surface (R-4): KNOWLEDGE_ROOT, PLATFORM_MAP, PLATFORM_RMAP,
                                 SITE_PATHS, LOCALE_RE → all now in content_discovery.

    This is the canonical baseline: if this test fails, an extraction sprint
    has removed a symbol without updating its consumers.
    """
    from knowledge_core import Knowledge, diff
    assert callable(Knowledge)
    assert callable(diff)


# ---------------------------------------------------------------------------
# R-4 migration complete — constants now in content_discovery
# ---------------------------------------------------------------------------

def test_constants_not_in_knowledge_core():
    """Confirm R-4 migration: constants removed from knowledge_core."""
    import knowledge_core as kc
    for sym in ("KNOWLEDGE_ROOT", "PLATFORM_MAP", "PLATFORM_RMAP", "SITE_PATHS", "LOCALE_RE"):
        assert not hasattr(kc, sym), f"{sym} should have moved to content_discovery"


def test_platform_map_importable_from_content_discovery():
    from content_discovery import PLATFORM_MAP
    assert isinstance(PLATFORM_MAP, dict)


def test_platform_rmap_importable_from_content_discovery():
    from content_discovery import PLATFORM_RMAP
    assert isinstance(PLATFORM_RMAP, dict)


def test_site_paths_importable_from_content_discovery():
    from content_discovery import SITE_PATHS
    assert isinstance(SITE_PATHS, list)


def test_locale_re_importable_from_content_discovery():
    import re
    from content_discovery import LOCALE_RE
    assert isinstance(LOCALE_RE, type(re.compile("")))


# ---------------------------------------------------------------------------
# Behavioral smoke tests — not just importable, but functional
# ---------------------------------------------------------------------------

def test_platform_map_is_empty():
    """PLATFORM_MAP is intentionally empty (API compat; paths now use canonical names)."""
    from content_discovery import PLATFORM_MAP
    assert PLATFORM_MAP == {}


def test_platform_rmap_is_empty():
    """PLATFORM_RMAP is intentionally empty (API compat)."""
    from content_discovery import PLATFORM_RMAP
    assert PLATFORM_RMAP == {}


def test_site_paths_has_five_sites():
    """SITE_PATHS must contain exactly 5 (site, path_pattern) tuples."""
    from content_discovery import SITE_PATHS
    assert len(SITE_PATHS) == 5
    sites = [s for s, _ in SITE_PATHS]
    assert "docs.aspose.org" in sites
    assert "products.aspose.org" in sites
    assert "reference.aspose.org" in sites
    assert "blog.aspose.org" in sites
    assert "kb.aspose.org" in sites


def test_locale_re_matches_locale_suffix():
    """LOCALE_RE must match locale-suffixed filenames."""
    from content_discovery import LOCALE_RE
    assert LOCALE_RE.search("_index.de.md")
    assert LOCALE_RE.search("page.fr.md")
    assert LOCALE_RE.search("guide.zh.md")


def test_locale_re_does_not_match_plain_md():
    """LOCALE_RE must not match plain .md files."""
    from content_discovery import LOCALE_RE
    assert not LOCALE_RE.search("_index.md")
    assert not LOCALE_RE.search("page.md")


def test_infer_product_returns_none_for_unknown_path():
    """infer_product(unknown_path) returns (None, None). Imported from canonical module."""
    from content_discovery import infer_product
    result = infer_product(Path("/some/random/path/file.md"))
    assert result == (None, None)
