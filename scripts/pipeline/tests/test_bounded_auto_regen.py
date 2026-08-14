"""Tests for commands/ops/bounded_auto_regen.py — bounded selection logic.

Pure selection tests (select_candidates) never touch I/O beyond the injected
changed/drift_state args. run() tests inject fake regen/lock/commit callables --
the real S-12->S-14 chain, the real regen lock, and git_plumb_commit.py are never
invoked here, matching the plan's "S-12/S-14 mocked, not invoked" requirement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops import bounded_auto_regen as bar


def _entry(family, platform, impact, stored="old", current="new"):
    return {"family": family, "platform": platform, "impact": impact,
            "stored_sha": stored, "current_sha": current}


class TestSelectCandidates:
    def test_high_impact_never_auto_regenerates(self):
        changed = [_entry("cells", "net", "HIGH")]
        result = bar.select_candidates(changed, {})
        assert result["auto_regen"] == []
        assert len(result["route_to_issue"]) == 1
        assert "never auto-regenerates" in result["route_to_issue"][0]["reason"]

    def test_low_and_medium_are_eligible(self):
        changed = [_entry("cells", "net", "LOW"), _entry("cells", "go", "MEDIUM")]
        result = bar.select_candidates(changed, {})
        selected = {(e["family"], e["platform"]) for e in result["auto_regen"]}
        assert selected == {("cells", "net"), ("cells", "go")}
        assert result["route_to_issue"] == []

    def test_unknown_impact_routes_to_issue(self):
        changed = [_entry("cells", "net", None)]
        result = bar.select_candidates(changed, {})
        assert result["auto_regen"] == []
        assert len(result["route_to_issue"]) == 1

    def test_cap_enforced(self):
        changed = [_entry("cells", p, "LOW") for p in ["a", "b", "c", "d", "e"]]
        result = bar.select_candidates(changed, {}, cap=3)
        assert len(result["auto_regen"]) == 3
        assert len(result["route_to_issue"]) == 2
        assert all("beyond per-run cap" in e["reason"] for e in result["route_to_issue"])

    def test_oldest_flagged_first_within_cap(self):
        changed = [_entry("cells", p, "LOW") for p in ["a", "b", "c", "d"]]
        drift_state = {
            "cells/a": {"consecutive_weeks_flagged": 1},
            "cells/b": {"consecutive_weeks_flagged": 5},
            "cells/c": {"consecutive_weeks_flagged": 3},
            "cells/d": {"consecutive_weeks_flagged": 0},
        }
        result = bar.select_candidates(changed, drift_state, cap=2)
        selected = [(e["family"], e["platform"]) for e in result["auto_regen"]]
        assert selected == [("cells", "b"), ("cells", "c")]  # 5 and 3 weeks, highest first

    def test_no_weeks_flagged_metadata_defaults_to_zero(self):
        changed = [_entry("cells", "net", "LOW")]
        result = bar.select_candidates(changed, {})  # empty drift_state
        assert len(result["auto_regen"]) == 1

    def test_selected_entries_do_not_leak_internal_sort_key(self):
        changed = [_entry("cells", "net", "LOW")]
        result = bar.select_candidates(changed, {"cells/net": {"consecutive_weeks_flagged": 2}})
        assert "_weeks_flagged" not in result["auto_regen"][0]

    def test_empty_changed_list_selects_nothing(self):
        result = bar.select_candidates([], {})
        assert result == {"auto_regen": [], "route_to_issue": []}


class _FakeLock:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class TestRun:
    def test_regenerates_and_commits_selected_products(self):
        changed = [_entry("cells", "net", "LOW")]
        regen_calls = []
        commit_calls = []
        lock = _FakeLock()

        def regen_fn(family, platform):
            regen_calls.append((family, platform))
            return True

        def try_lock(family, platform):
            return lock

        def commit_fn(family, platform, message):
            commit_calls.append((family, platform, message))
            return True

        result = bar.run(regen_fn=regen_fn, try_acquire_lock=try_lock, commit_fn=commit_fn,
                          changed=changed, drift_state={})
        assert regen_calls == [("cells", "net")]
        assert len(commit_calls) == 1
        assert result["regenerated"] == changed
        assert lock.released is True

    def test_skips_but_does_not_block_on_lock_contention(self):
        changed = [_entry("cells", "net", "LOW")]
        regen_calls = []

        def regen_fn(family, platform):
            regen_calls.append((family, platform))
            return True

        def try_lock(family, platform):
            return None  # contended

        result = bar.run(regen_fn=regen_fn, try_acquire_lock=try_lock, changed=changed, drift_state={})
        assert regen_calls == []
        assert len(result["skipped_locked"]) == 1
        assert result["regenerated"] == []

    def test_failed_regen_recorded_and_not_committed(self):
        changed = [_entry("cells", "net", "LOW")]
        commit_calls = []

        def regen_fn(family, platform):
            return False

        def try_lock(family, platform):
            return _FakeLock()

        def commit_fn(family, platform, message):
            commit_calls.append(1)
            return True

        result = bar.run(regen_fn=regen_fn, try_acquire_lock=try_lock, commit_fn=commit_fn,
                          changed=changed, drift_state={})
        assert result["failed"] == [{**changed[0], "reason": "regen chain failed"}]
        assert commit_calls == []

    def test_lock_released_even_when_regen_raises(self):
        changed = [_entry("cells", "net", "LOW")]
        lock = _FakeLock()

        def regen_fn(family, platform):
            raise RuntimeError("boom")

        def try_lock(family, platform):
            return lock

        with pytest.raises(RuntimeError):
            bar.run(regen_fn=regen_fn, try_acquire_lock=try_lock, changed=changed, drift_state={})
        assert lock.released is True

    def test_high_impact_products_never_reach_regen_fn(self):
        changed = [_entry("cells", "net", "HIGH")]
        regen_calls = []

        def regen_fn(family, platform):
            regen_calls.append((family, platform))
            return True

        def try_lock(family, platform):
            return _FakeLock()

        result = bar.run(regen_fn=regen_fn, try_acquire_lock=try_lock, changed=changed, drift_state={})
        assert regen_calls == []
        assert len(result["route_to_issue"]) == 1

    def test_commit_fn_optional(self):
        changed = [_entry("cells", "net", "LOW")]

        def regen_fn(family, platform):
            return True

        def try_lock(family, platform):
            return _FakeLock()

        result = bar.run(regen_fn=regen_fn, try_acquire_lock=try_lock, changed=changed, drift_state={})
        assert result["regenerated"] == changed


class TestCLI:
    def test_select_command_runs_without_error(self, tmp_path, capsys):
        bar.configure(repo_root=tmp_path)
        try:
            rc = bar.main(["select"])
            assert rc == 0
            out = capsys.readouterr().out
            assert "Auto-regen (0)" in out
        finally:
            bar.configure(repo_root=None)
