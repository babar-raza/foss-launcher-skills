"""Behavioral-equivalence tests: does the ported LOGIC actually match
aspose.org's, not just "look similar on read-through"?

New 2026-08-29, closes TASK_BACKLOG.md SYNC-9's first slice: "functional
parity" claims across this repo's history have all been prose/read-through
judgments, never verified by running source's and target's actual code
against identical input and diffing the output. This file does that, for
the 3 artifacts in the 2026-08-29 sync whose logic is supposed to be
LITERALLY equivalent (near-verbatim or lightly-adapted ports) -- not for
the llms-* family, whose backing scripts were deliberately rewritten
(different subdomain iteration, different output shape), so there is no
meaningful "same input, same output" comparison to make there; that
distinction is itself a finding, not an oversight -- see
docs/parity/source-anchors.yaml's generalization notes per artifact.

Requires SOURCE_REPO_PATH (the aspose.org checkout). Skips cleanly when
unset -- same posture as detect_source_drift.py: this is not a CI gate on
runners without the source repo available, it's an agent/session-invoked
proof. Imports source modules READ-ONLY (a plain Python import never
writes to the source repo).
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_REPO_PATH = os.environ.get("SOURCE_REPO_PATH", "")

pytestmark = pytest.mark.skipif(
    not SOURCE_REPO_PATH, reason="SOURCE_REPO_PATH not set -- behavioral-equivalence proof needs aspose.org checked out"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_session_identity():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "pipeline" / "lib" / "session_identity.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_session_identity", path)


@pytest.fixture
def target_session_identity():
    path = REPO_ROOT / "scripts" / "pipeline" / "lib" / "session_identity.py"
    return _load_module("target_session_identity", path)


_IDENTITY_ENV_MATRIX = [
    {},
    {"AGENT_SESSION_ID": "abc-123"},
    {"CODEX_THREAD_ID": "codex-xyz"},
    {"CLAUDE_CODE_SESSION_ID": "claude-session-1"},
    {"AGENT_SESSION_ID": "abc-123", "CODEX_THREAD_ID": "codex-xyz", "CLAUDE_CODE_SESSION_ID": "claude-session-1"},
    {"CODEX_THREAD_ID": "codex-xyz", "CLAUDE_CODE_SESSION_ID": "claude-session-1"},
    {"AGENT_SESSION_ID": "   "},  # whitespace-only, must be treated as unset
]


@pytest.mark.parametrize("env", _IDENTITY_ENV_MATRIX)
def test_session_identity_resolve_matches_source(monkeypatch, source_session_identity, target_session_identity, env):
    for key in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert source_session_identity.resolve() == target_session_identity.resolve()


@pytest.mark.parametrize("raw", ["abc/def:ghi 123", "plain-id", "a" * 100, "with spaces  and\ttabs"])
def test_session_identity_sanitize_matches_source(source_session_identity, target_session_identity, raw):
    assert source_session_identity.sanitize(raw) == target_session_identity.sanitize(raw)


def test_session_identity_resolve_sanitized_matches_source(monkeypatch, source_session_identity, target_session_identity):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "weird id/with:chars")
    assert source_session_identity.resolve_sanitized() == target_session_identity.resolve_sanitized()


@pytest.fixture
def source_check_module_consumption():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "ci" / "checks" / "check_module_consumption.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_check_module_consumption", path)


@pytest.fixture
def target_check_module_consumption():
    path = REPO_ROOT / "scripts" / "ci" / "checks" / "check_module_consumption.py"
    return _load_module("target_check_module_consumption", path)


def test_find_real_consumers_matches_source_on_identical_fixture(
    tmp_path, source_check_module_consumption, target_check_module_consumption
):
    """Ported with NO functional changes (per docs/parity/source-anchors.yaml's
    own notes) -- this proves that claim, not just asserts it."""
    scan_root = tmp_path / "scripts"
    scan_root.mkdir()
    (scan_root / "my_module.py").write_text("x = 1\n", encoding="utf-8")
    (scan_root / "caller_a.py").write_text("from my_module import x\n", encoding="utf-8")
    (scan_root / "test_my_module.py").write_text("import my_module\n", encoding="utf-8")
    (scan_root / "unrelated.py").write_text("y = 2\n", encoding="utf-8")

    source_result = source_check_module_consumption.find_real_consumers(
        "scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path
    )
    target_result = target_check_module_consumption.find_real_consumers(
        "scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path
    )
    assert source_result == target_result
    assert [p.name for p in source_result] == ["caller_a.py"]


@pytest.fixture
def source_check_stale_file_regression():
    path = Path(SOURCE_REPO_PATH) / "scripts" / "ci" / "checks" / "check_stale_file_regression.py"
    if not path.is_file():
        pytest.skip(f"source file not found at expected path: {path}")
    return _load_module("source_check_stale_file_regression", path)


@pytest.fixture
def target_check_stale_file_regression():
    path = REPO_ROOT / "scripts" / "ci" / "checks" / "check_stale_file_regression.py"
    return _load_module("target_check_stale_file_regression", path)


_REGRESSION_MATRIX = [
    ("old", "old", "new"),      # silent revert -> True
    ("new", "old", "new"),      # already incorporates the change -> False
    ("other", "old", "new"),    # neither match -> False
    ("old", "old", None),       # intervening had no comparable blob -> False
    ("old", None, "new"),       # file newly created by intervening -> False
]


@pytest.mark.parametrize("proposed,parent,intervening", _REGRESSION_MATRIX)
def test_detect_regression_matches_source(
    source_check_stale_file_regression, target_check_stale_file_regression, proposed, parent, intervening
):
    source_result = source_check_stale_file_regression.detect_regression(proposed, parent, intervening)
    target_result = target_check_stale_file_regression.detect_regression(proposed, parent, intervening)
    assert source_result == target_result
