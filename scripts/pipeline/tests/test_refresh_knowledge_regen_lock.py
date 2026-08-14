"""Tests for refresh_knowledge.py's regen-lock wiring (FRESH-001 T4).

The scout->enrich->promote->index chain (and this module's own merged/<->merged.bak
backup-restore around it) previously had no lock at all. refresh() now wraps that
chain in knowledge_regen_lock.acquire_regen_lock() -- these tests prove the lock is
actually held during the chain and that contention degrades to "failed" instead of
racing on the same merged/merged.bak directories.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import refresh_knowledge as _rk
from knowledge_regen_lock import acquire_regen_lock, regen_lock_path


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _rk.configure(repo_root=tmp_path)
    yield
    _rk.configure()


def _patch_head(sha):
    return patch.object(_rk, "_head_sha", return_value=sha)


def _patch_model(sha):
    return patch.object(_rk, "_model_sha", return_value=sha)


class TestRegenLockWiring:
    def test_stale_refresh_acquires_and_releases_the_regen_lock(self, tmp_path):
        lock_path = regen_lock_path("cells", "python", knowledge_root=_rk.KNOWLEDGE_ROOT)
        held_during_chain = {}

        def _fake_run(cmd, label):
            held_during_chain[label] = lock_path.is_file()
            return True

        with _patch_head("newsha"), _patch_model("oldsha"), \
             patch.object(_rk, "_clone_dir", return_value=tmp_path / "clone"), \
             patch.object(_rk, "_update_clone", return_value=None), \
             patch.object(_rk, "_compute_extractor_hash", return_value="h1"), \
             patch.object(_rk, "_stored_extractor_hash", return_value="h1"), \
             patch.object(_rk, "_run", side_effect=_fake_run), \
             patch.object(_rk, "_run_completeness_check"):
            result = _rk.refresh("cells", "python", skip_enrich=True)

        assert result == "refreshed"
        assert held_during_chain.get("scout") is True, "lock must be held while scout runs"
        assert held_during_chain.get("promote") is True, "lock must be held while promote runs"
        assert not lock_path.exists(), "lock must be released after the chain completes"

    def test_contended_lock_returns_failed_without_running_chain(self, tmp_path):
        chain_called = {"value": False}

        def _fake_run(cmd, label):
            chain_called["value"] = True
            return True

        held_lock = acquire_regen_lock(
            "cells", "python", owner="other-session",
            knowledge_root=_rk.KNOWLEDGE_ROOT, timeout=0.2,
        )
        held_lock.acquire()
        try:
            with _patch_head("newsha"), _patch_model("oldsha"), \
                 patch.object(_rk, "_clone_dir", return_value=tmp_path / "clone"), \
                 patch.object(_rk, "_update_clone", return_value=None), \
                 patch.object(_rk, "_compute_extractor_hash", return_value="h1"), \
                 patch.object(_rk, "_stored_extractor_hash", return_value="h1"), \
                 patch.object(_rk, "_run", side_effect=_fake_run):
                result = _rk.refresh("cells", "python", skip_enrich=True)
        finally:
            held_lock.release()

        assert result == "failed"
        assert chain_called["value"] is False, "chain must never run while another owner holds the lock"

    def test_lock_released_even_when_scout_fails(self, tmp_path):
        lock_path = regen_lock_path("cells", "python", knowledge_root=_rk.KNOWLEDGE_ROOT)

        with _patch_head("newsha"), _patch_model("oldsha"), \
             patch.object(_rk, "_clone_dir", return_value=tmp_path / "clone"), \
             patch.object(_rk, "_update_clone", return_value=None), \
             patch.object(_rk, "_compute_extractor_hash", return_value="h1"), \
             patch.object(_rk, "_stored_extractor_hash", return_value="h1"), \
             patch.object(_rk, "_run", return_value=False):  # scout fails immediately
            result = _rk.refresh("cells", "python", skip_enrich=True)

        assert result == "failed"
        assert not lock_path.exists(), "lock must be released even when the chain fails"
