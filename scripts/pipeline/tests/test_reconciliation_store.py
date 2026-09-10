"""Tests for reconciliation_store.py (PKGINSTALL-RECONCILIATION-STORE)."""
import json
import threading
from pathlib import Path

import pytest

import reconciliation_store as sut


def _row(path: str, family: str = "cells", platform: str = "net", **overrides) -> dict:
    base = {
        "path": path,
        "family": family,
        "platform": platform,
        "site": "docs.aspose.org",
        "locale": "en",
        "representation": "literal",
        "registry_type": "nuget",
        "published": False,
        "collision_classification": "SAFE_FOR_MECHANICAL_MIGRATION",
        "finding_count_literal": 1,
        "finding_count_install_recipe_fail": 0,
        "sweep_run_id": "sweep-20260910-000000-abc123",
        "base_sha": "abc123",
        "recorded_at": "2026-09-10T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestAppendBatchAndRead:
    def test_round_trips_a_fixture_batch(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        batch = [_row("content/a.md"), _row("content/b.md")]
        written = store.append_batch(batch)
        assert written == 2

        latest = store.read_latest()
        assert set(latest) == {"content/a.md", "content/b.md"}
        assert latest["content/a.md"]["family"] == "cells"

    def test_empty_batch_is_a_noop(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        assert store.append_batch([]) == 0
        assert store.read_history() == []

    def test_read_history_returns_append_order(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row("content/a.md")])
        store.append_batch([_row("content/b.md")])
        history = store.read_history()
        assert [r["path"] for r in history] == ["content/a.md", "content/b.md"]

    def test_read_latest_for_product_filters_correctly(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            _row("content/a.md", family="cells", platform="net"),
            _row("content/b.md", family="slides", platform="net"),
        ])
        subset = store.read_latest_for_product("cells", "net")
        assert set(subset) == {"content/a.md"}


class TestLastOccurrenceWins:
    def test_same_path_in_two_batches_uses_the_newer_row(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row("content/a.md", sweep_run_id="sweep-1", finding_count_literal=5)])
        store.append_batch([_row("content/a.md", sweep_run_id="sweep-2", finding_count_literal=0)])
        latest = store.read_latest()
        assert latest["content/a.md"]["sweep_run_id"] == "sweep-2"
        assert latest["content/a.md"]["finding_count_literal"] == 0


class TestValidation:
    def test_invalid_representation_rejected(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        bad = _row("content/a.md", representation="not_a_real_value")
        with pytest.raises(ValueError):
            store.append_batch([bad])
        # Nothing written -- not even the file itself.
        assert not store.path.exists()

    def test_missing_required_field_rejected(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        bad = _row("content/a.md")
        del bad["sweep_run_id"]
        with pytest.raises(ValueError):
            store.append_batch([bad])

    def test_partially_bad_batch_writes_nothing(self, tmp_path):
        """One invalid record in a batch of otherwise-valid ones must refuse
        the whole batch -- never a partial write."""
        store = sut.ReconciliationStore(repo_root=tmp_path)
        batch = [_row("content/a.md"), _row("content/b.md", collision_classification="BOGUS")]
        with pytest.raises(ValueError):
            store.append_batch(batch)
        assert store.read_history() == []


class TestCorruptionTolerance:
    def test_torn_last_line_is_skipped_not_raised(self, tmp_path):
        store = sut.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row("content/a.md")])
        with open(store.path, "a", encoding="utf-8") as f:
            f.write('{"path": "content/b.md", "incomplete tor')  # simulated crashed write
        history = store.read_history()
        assert [r["path"] for r in history] == ["content/a.md"]


class TestConcurrentWrites:
    def test_two_threads_appending_never_corrupts_the_file(self, tmp_path):
        store_a = sut.ReconciliationStore(repo_root=tmp_path)
        store_b = sut.ReconciliationStore(repo_root=tmp_path)
        errors = []

        def _write(store, prefix, n):
            try:
                store.append_batch([_row(f"content/{prefix}-{i}.md") for i in range(n)])
            except Exception as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        t1 = threading.Thread(target=_write, args=(store_a, "a", 25))
        t2 = threading.Thread(target=_write, args=(store_b, "b", 25))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert errors == []
        history = store_a.read_history()
        assert len(history) == 50
        # Every line must be independently valid JSON -- proof neither
        # writer's batch got interleaved mid-line with the other's.
        for line in store_a.path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
