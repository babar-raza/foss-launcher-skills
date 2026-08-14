"""Tests for lib/knowledge_regen_lock.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
_LIB_DIR = _PIPELINE_DIR / "lib"
for p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from advisory_lock import LockTimeout
import knowledge_regen_lock as krl


class TestRegenLockPath:
    def test_co_located_with_merged_dir(self, tmp_path):
        path = krl.regen_lock_path("cells", "net", knowledge_root=tmp_path)
        assert path == tmp_path / "cells" / "net" / "merged" / ".regen.lock"


class TestAcquireRegenLock:
    def test_acquire_creates_lock_file_with_owner_suffix(self, tmp_path):
        lock = krl.acquire_regen_lock("cells", "net", owner="manual", knowledge_root=tmp_path)
        with lock:
            payload = lock.path.read_text(encoding="utf-8")
            parts = payload.split(":")
            assert len(parts) == 3
            assert parts[2] == "manual"
        assert not lock.path.exists(), "lock file must be removed on release"

    def test_release_actually_removes_the_lock_it_holds(self, tmp_path):
        """Regression test: acquire() rewrites the payload to append ':owner',
        which must stay in sync with FileLock's own compare-then-unlink safety
        check in release() -- otherwise release() sees a "changed" payload and
        refuses to unlink a lock it legitimately still holds."""
        lock = krl.acquire_regen_lock("cells", "net", owner="manual", knowledge_root=tmp_path)
        lock.acquire()
        assert lock.path.exists()
        lock.release()
        assert not lock.path.exists()

    def test_second_acquire_for_same_product_blocks_until_released(self, tmp_path):
        lock1 = krl.acquire_regen_lock("cells", "net", owner="manual", knowledge_root=tmp_path, timeout=0.3)
        lock1.acquire()

        lock2 = krl.acquire_regen_lock("cells", "net", owner="scheduled-sweep", knowledge_root=tmp_path, timeout=0.3)
        with pytest.raises(LockTimeout):
            lock2.acquire()

        lock1.release()
        # now lock2 can succeed
        lock2.acquire()
        lock2.release()

    def test_different_products_do_not_contend(self, tmp_path):
        lock_net = krl.acquire_regen_lock("cells", "net", owner="manual", knowledge_root=tmp_path)
        lock_go = krl.acquire_regen_lock("cells", "go", owner="manual", knowledge_root=tmp_path)
        lock_net.acquire()
        lock_go.acquire()  # must not block/raise -- different lock paths
        lock_net.release()
        lock_go.release()

    def test_context_manager_releases_on_exception(self, tmp_path):
        lock_path = krl.regen_lock_path("cells", "net", knowledge_root=tmp_path)
        with pytest.raises(ValueError):
            with krl.acquire_regen_lock("cells", "net", owner="manual", knowledge_root=tmp_path):
                raise ValueError("simulated failure mid-chain")
        assert not lock_path.exists()


class TestInspectLock:
    def test_none_when_no_lock_file(self, tmp_path):
        assert krl.inspect_lock("cells", "net", knowledge_root=tmp_path) is None

    def test_reports_pid_and_owner_while_held(self, tmp_path):
        lock = krl.acquire_regen_lock("cells", "net", owner="refresh-product", knowledge_root=tmp_path)
        with lock:
            info = krl.inspect_lock("cells", "net", knowledge_root=tmp_path)
            assert info is not None
            assert info["owner"] == "refresh-product"
            assert info["pid"] > 0
            assert info["age_seconds"] >= 0

    def test_none_after_release(self, tmp_path):
        lock = krl.acquire_regen_lock("cells", "net", owner="manual", knowledge_root=tmp_path)
        with lock:
            pass
        assert krl.inspect_lock("cells", "net", knowledge_root=tmp_path) is None
