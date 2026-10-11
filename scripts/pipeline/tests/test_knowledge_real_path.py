"""P5 hardening — runtime validation against real knowledge directory.

These tests exercise the default unpatched code path:
  content_discovery.KNOWLEDGE_ROOT → knowledge_core._KNOWLEDGE_ROOT
  → Knowledge.__init__ → real disk read → populated model.

All current unit tests use synthetic fixture directories with knowledge_root= override.
These tests prove the full real-disk path works end-to-end without any monkeypatch.

Both tests are guarded with skipif: the knowledge/ directory is gitignored and absent
on CI machines without a knowledge-build step. Tests skip cleanly rather than fail.

Confirmed working real family/platform: cells/python (merged/ dir with api_surface.json,
model.yaml, claims.json).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from content_discovery import KNOWLEDGE_ROOT  # noqa: E402

REAL_CELLS_MERGED = KNOWLEDGE_ROOT / "cells" / "python" / "merged"
REAL_CELLS_API_SURFACE = REAL_CELLS_MERGED / "api_surface.json"


@pytest.mark.skipif(
    not REAL_CELLS_API_SURFACE.exists(),
    reason="real knowledge directory not present (gitignored; skip in CI)",
)
def test_knowledge_loads_from_real_directory_without_monkeypatch():
    """Knowledge() uses content_discovery.KNOWLEDGE_ROOT unpatched.

    Proves: KNOWLEDGE_ROOT → _KNOWLEDGE_ROOT → Knowledge.__init__ → real disk read.
    """
    from knowledge_core import Knowledge

    k = Knowledge("cells", "python")
    assert k.available, "Knowledge should be available when real merged/ dir exists"
    assert k.classes, "Knowledge.classes should be non-empty for cells/python"
    assert k.repo_sha, "Knowledge.repo_sha should be non-empty"


@pytest.mark.skipif(
    not REAL_CELLS_API_SURFACE.exists(),
    reason="real knowledge directory not present (gitignored; skip in CI)",
)
def test_knowledge_root_private_matches_content_discovery_constant():
    """_KNOWLEDGE_ROOT in knowledge_core matches KNOWLEDGE_ROOT in content_discovery.

    Proves the private alias import in knowledge_core (R-4) is wired to the same
    Path object as the public constant in content_discovery.
    """
    import knowledge_core as kc

    assert kc._KNOWLEDGE_ROOT == KNOWLEDGE_ROOT
