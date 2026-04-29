"""Pytest configuration for pipeline tests.

This is the ONE legitimate place in the pipeline codebase for
sys.path.insert.  All other production scripts have it removed because
Python adds the script directory automatically when invoked directly;
pytest does not do this, so conftest.py must do it for tests.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

# Add scripts/pipeline/ to sys.path so all pipeline modules are importable
# without dotted-path prefixes (e.g. `import audit` not `import scripts.pipeline.audit`).
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

# Add lib/ and all commands/ subdirectories so bare imports of moved modules
# (e.g. `from knowledge_core import Knowledge`) continue to work in tests.
# IMPORTANT: commands/ dirs are appended (not inserted) to avoid shadowing
# pipeline packages like audit/ with commands/content/audit.py.
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_COMMANDS_DIR = _PIPELINE_ROOT / "commands"
if _COMMANDS_DIR.is_dir():
    for _sub in sorted(_COMMANDS_DIR.iterdir()):
        if _sub.is_dir() and not _sub.name.startswith("_"):
            _p = str(_sub)
            if _p not in sys.path:
                sys.path.append(_p)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fake_knowledge(tmp_path):
    """A Knowledge instance loaded from the synthetic fixtures in tests/fixtures/.

    Creates a temporary knowledge directory structure and returns a loaded
    ``Knowledge`` object.  Tests that use this fixture never touch the real
    ``knowledge/`` directory on disk.

    Fixture files:
        fake_api_surface.json  → merged/api_surface.json
        fake_model.yaml        → merged/model.yaml
        fake_claims.json       → merged/claims.json
        fake_formats.json      → merged/formats.json
    """
    # Build knowledge dir: <tmp>/knowledge/fake/python/merged/
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)

    shutil.copy(_FIXTURES_DIR / "fake_api_surface.json", merged / "api_surface.json")
    shutil.copy(_FIXTURES_DIR / "fake_model.yaml", merged / "model.yaml")
    shutil.copy(_FIXTURES_DIR / "fake_claims.json", merged / "claims.json")
    shutil.copy(_FIXTURES_DIR / "fake_formats.json", merged / "formats.json")

    from knowledge_core import Knowledge

    return Knowledge("fake", "python", knowledge_root=tmp_path / "knowledge")
