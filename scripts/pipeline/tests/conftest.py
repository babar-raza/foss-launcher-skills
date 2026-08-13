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


@pytest.fixture(autouse=True)
def _isolate_knowledge_state_globally(tmp_path, monkeypatch):
    """MT030-2026-08-13: never let ANY test in this suite write to the real
    repo-root data/knowledge_state.json or data/upstream_baselines.json.

    promote.py, truth_audit.py, and evidence/runner.py now call into
    knowledge_state.py's durable writer as a side effect of their normal
    operation (non-fatal, but real) -- and a real, non-hypothetical incident
    during this same mission proved the risk: an early, not-yet-isolated test
    run of test_promote_integration.py wrote family="test"/platform="python"
    into the actual data/knowledge_state.json and data/upstream_baselines.json,
    and a later FULL SUITE run reintroduced it (plus "test/testplat") through a
    completely different test file (test_merge_determinism.py and others all
    call promote()/attach_evidence() for real with synthetic family="test"
    fixtures, none of which anticipated this new side effect). Per-file opt-in
    isolation does not scale to "every current and future test that might
    exercise these code paths" -- this fixture makes it structural instead.

    Patches BOTH possible module-object identities for knowledge_state.py:
    conftest.py puts both scripts/pipeline/ and scripts/pipeline/lib/ on
    sys.path, so `import knowledge_state` and `from lib.knowledge_state import
    ...` can resolve to two DISTINCT module objects with independent globals
    (confirmed live -- see test_promote_integration.py's
    TestPromoteKnowledgeStateWiring fixture comment for the same gotcha at
    single-file scope). A test that wants the REAL knowledge_state module
    object for direct assertions should import it fresh inside the test body
    (as scripts/pipeline/tests/test_knowledge_state.py and others already do)
    -- it will observe these same tmp_path-redirected globals, not the real
    file, since this fixture runs before test bodies via autouse.
    """
    state_path = tmp_path / "knowledge_state.json"
    lock_path = tmp_path / "knowledge_state.json.lock"
    baselines_path = tmp_path / "upstream_baselines.json"
    baselines_lock_path = tmp_path / "upstream_baselines.json.lock"

    import importlib
    for module_name in ("knowledge_state", "lib.knowledge_state"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        monkeypatch.setattr(module, "_STATE_PATH", state_path, raising=False)
        monkeypatch.setattr(module, "_LOCK_PATH", lock_path, raising=False)
        monkeypatch.setattr(module, "_UPSTREAM_BASELINES_PATH", baselines_path, raising=False)
        monkeypatch.setattr(module, "_UPSTREAM_BASELINES_LOCK_PATH", baselines_lock_path, raising=False)
    yield


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
