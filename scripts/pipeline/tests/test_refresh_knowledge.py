"""Tests for refresh_knowledge.py — subprocess sequencing and skip conditions.

Covers:
  - refresh() returns "no_clone" when clone cache is missing
  - refresh() returns "current" when model SHA matches HEAD
  - refresh() returns "stale" in check_only mode when SHA differs
  - refresh() calls scout → enrich → promote → index in correct order
  - refresh() with auto_clone=False does not attempt clone
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import refresh_knowledge as _rk
from refresh_knowledge import refresh


# ---------------------------------------------------------------------------
# Helper stubs
# ---------------------------------------------------------------------------

def _patch_head(sha: str | None):
    """Return a context manager that patches _head_sha to return *sha*."""
    return patch.object(_rk, "_head_sha", return_value=sha)


def _patch_model(sha: str | None):
    """Return a context manager that patches _model_sha to return *sha*."""
    return patch.object(_rk, "_model_sha", return_value=sha)


def _patch_clone_dir(tmp_path: Path):
    """Return a context manager that patches _clone_dir to return a temp path."""
    return patch.object(_rk, "_clone_dir", return_value=tmp_path / "clone")


# ---------------------------------------------------------------------------
# no_clone path
# ---------------------------------------------------------------------------

class TestRefreshNoClone:
    def test_returns_no_clone_when_head_is_none(self, tmp_path):
        with _patch_clone_dir(tmp_path), _patch_head(None):
            result = refresh("cells", "python", auto_clone=False)
        assert result == "no_clone"

    def test_no_clone_with_auto_clone_false(self, tmp_path):
        """Even with HEAD=None, auto_clone=False prevents clone attempt."""
        with _patch_clone_dir(tmp_path), _patch_head(None), \
             patch.object(_rk, "_try_auto_clone") as mock_clone:
            result = refresh("cells", "python", auto_clone=False)
        mock_clone.assert_not_called()
        assert result == "no_clone"

    def test_auto_clone_attempted_when_head_none(self, tmp_path):
        """auto_clone=True (default) attempts clone when HEAD is missing."""
        with _patch_clone_dir(tmp_path), \
             patch.object(_rk, "_head_sha", side_effect=[None, None]), \
             patch.object(_rk, "_try_auto_clone", return_value=False) as mock_clone:
            result = refresh("cells", "python", auto_clone=True)
        mock_clone.assert_called_once()
        assert result == "no_clone"


# ---------------------------------------------------------------------------
# current path
# ---------------------------------------------------------------------------

class TestRefreshCurrent:
    def test_returns_current_when_sha_matches(self, tmp_path):
        sha = "abc123deadbeef"
        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha):
            result = refresh("cells", "python")
        assert result == "current"

    def test_current_does_not_call_run(self, tmp_path):
        sha = "abc123deadbeef"
        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
             patch.object(_rk, "_run") as mock_run:
            refresh("cells", "python")
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# check_only path (stale detection without running pipeline)
# ---------------------------------------------------------------------------

class TestRefreshCheckOnly:
    def test_returns_stale_when_sha_differs(self, tmp_path):
        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"):
            result = refresh("cells", "python", check_only=True)
        assert result == "stale"

    def test_check_only_does_not_call_run(self, tmp_path):
        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
             patch.object(_rk, "_run") as mock_run:
            refresh("cells", "python", check_only=True)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Full refresh — step sequencing
# ---------------------------------------------------------------------------

class TestRefreshSequencing:
    def test_scout_called_before_promote(self, tmp_path):
        """scout must run before promote; verify call ordering."""
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert call_order.index("scout") < call_order.index("promote"), (
            "scout must be called before promote"
        )

    def test_enrich_called_after_scout(self, tmp_path):
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            refresh("cells", "python")

        assert "enrich" in call_order
        assert call_order.index("scout") < call_order.index("enrich")

    def test_index_called_after_promote(self, tmp_path):
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            refresh("cells", "python")

        assert "index" in call_order
        assert call_order.index("promote") < call_order.index("index")

    def test_returns_failed_when_scout_fails(self, tmp_path):
        def fake_run(cmd: list[str], label: str) -> bool:
            return False  # all steps fail

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "failed"

    def test_returns_failed_when_promote_fails(self, tmp_path):
        def fake_run(cmd: list[str], label: str) -> bool:
            return label != "promote"

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "failed"

    def test_enrich_failure_does_not_stop_pipeline(self, tmp_path):
        """enrich is best-effort: failure should not stop promote/index."""
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return label != "enrich"  # enrich fails, rest succeed

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert "promote" in call_order
        assert "index" in call_order
