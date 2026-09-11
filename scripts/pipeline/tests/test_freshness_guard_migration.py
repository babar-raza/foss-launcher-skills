"""Behavioral-equivalence tests for the freshness_guard migration (FRESH-001 T7).

Each of batch_reference.py, refresh_run.py, launch_gate.py, and readiness_gate.py was
migrated from a raw `model.yaml["stale_since"] is not None` check to
`freshness_guard.is_generation_allowed(mode="degraded")`. These tests prove the new
gate is a superset of the old behavior on the two cases the old check could express
(stale_since None -> allow, stale_since set -> block) at each of the 4 call sites, so
a regression in the shared function surfaces close to its source rather than only in
the launch-blocking call sites migrated last.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
_LIB_DIR = _PIPELINE_DIR / "lib"
for p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import freshness_guard as fg


@pytest.fixture(autouse=True)
def _configure(tmp_path, monkeypatch):
    fg.configure(repo_root=tmp_path)
    # RC-freshness-guard-tree-identity (readme-refresh-hardening-and-regen-2026-08-30, TC-11):
    # without this, the new reachability check would resolve core.clone_cache against the REAL
    # repo's runs/.clone_cache/ (no configure() seam of its own) -- this file's tests use real
    # product names like "cells/net", which really do have real clones on this machine, so a
    # synthetic test repo_sha would be reported STALE_ORPHANED against real, unrelated clone
    # content instead of falling through to the pre-existing stale_since-only logic these tests
    # exist to prove is unchanged. See test_freshness_guard.py's identical fixture fix for the
    # full rationale.
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "_no_clone_cache"))
    yield
    fg.configure(repo_root=None)


def _write_model(tmp_path, family, platform, *, repo_sha="sha-1", stale_since=None):
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text(
        yaml.dump({"repo_sha": repo_sha, "stale_since": stale_since}), encoding="utf-8")
    return merged


class TestDegradedModeMatchesOldStaleSinceSemantics:
    """The exact two cases the old `stale_since is not None` check could express."""

    def test_stale_since_none_is_allowed(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since=None)
        allowed, result = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is True
        assert result.state == "CURRENT"

    def test_stale_since_set_is_blocked(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        allowed, result = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is False
        assert result.state == "STALE"


class TestBatchReferenceCallSite:
    def test_current_model_allows_generation(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import batch_reference as br
        br.configure(repo_root=tmp_path)
        try:
            merged = tmp_path / "knowledge" / "cells" / "net" / "merged"
            merged.mkdir(parents=True)
            (merged / "api_surface.json").write_text("[]", encoding="utf-8")
            (merged / "model.yaml").write_text(
                yaml.dump({"repo_sha": "sha-1", "stale_since": None, "version": "1.0"}),
                encoding="utf-8")
            # run() with 0 candidates should not hit the freshness STOP path
            result = br.run("cells", "net", run_id="EQUIV-TEST")
            assert result["generated"] == 0  # no candidates, but not a freshness SystemExit
        finally:
            br.configure()

    def test_stale_model_exits_before_generation(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import batch_reference as br
        br.configure(repo_root=tmp_path)
        try:
            merged = tmp_path / "knowledge" / "cells" / "net" / "merged"
            merged.mkdir(parents=True)
            (merged / "api_surface.json").write_text(
                json.dumps([{"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []}]),
                encoding="utf-8")
            (merged / "model.yaml").write_text(
                yaml.dump({"repo_sha": "sha-1", "stale_since": "2026-08-14", "version": "1.0"}),
                encoding="utf-8")
            with pytest.raises(SystemExit):
                br.run("cells", "net", run_id="EQUIV-TEST-STALE")
        finally:
            br.configure()


class TestRefreshRunCallSite:
    def test_model_state_returns_model_dict_when_current(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import refresh_run as rr
        rr.configure(repo_root=tmp_path)
        try:
            _write_model(tmp_path, "cells", "net", repo_sha="sha-1", stale_since=None)
            data = rr._model_state("cells", "net")
            assert data["repo_sha"] == "sha-1"
        finally:
            rr.configure()

    def test_model_state_raises_when_stale(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import refresh_run as rr
        rr.configure(repo_root=tmp_path)
        try:
            _write_model(tmp_path, "cells", "net", repo_sha="sha-1", stale_since="2026-08-14")
            with pytest.raises(rr.RefreshRunError):
                rr._model_state("cells", "net")
        finally:
            rr.configure()


class TestLaunchGateCallSite:
    def test_gate_l01_pass_when_current(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import launch_gate as lg
        lg.configure(repo_root=tmp_path)
        try:
            _write_model(tmp_path, "cells", "net", repo_sha="sha-1", stale_since=None)
            result = lg.gate_l01_knowledge_freshness("cells", "net")
            assert result.status == lg.STATUS_PASS
        finally:
            lg.configure()

    def test_gate_l01_fail_when_stale(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import launch_gate as lg
        lg.configure(repo_root=tmp_path)
        try:
            _write_model(tmp_path, "cells", "net", repo_sha="sha-1", stale_since="2026-08-14")
            result = lg.gate_l01_knowledge_freshness("cells", "net")
            assert result.status == lg.STATUS_FAIL
        finally:
            lg.configure()


class TestReadinessGateCallSite:
    def test_gate_g04_pass_when_current(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import readiness_gate as rg
        rg.configure(repo_root=tmp_path)
        try:
            _write_model(tmp_path, "cells", "net", repo_sha="sha-1", stale_since=None)
            result = rg.gate_g04_knowledge_staleness("cells", "net")
            assert result.status == rg.STATUS_PASS
        finally:
            rg.configure()

    def test_gate_g04_fail_when_stale(self, tmp_path):
        sys.path.insert(0, str(_PIPELINE_DIR))
        import readiness_gate as rg
        rg.configure(repo_root=tmp_path)
        try:
            _write_model(tmp_path, "cells", "net", repo_sha="sha-1", stale_since="2026-08-14")
            result = rg.gate_g04_knowledge_staleness("cells", "net")
            assert result.status == rg.STATUS_FAIL
        finally:
            rg.configure()


def _write_upstream_baselines(tmp_path, entries: dict):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "upstream_baselines.json").write_text(json.dumps(entries), encoding="utf-8")


class TestSitePlannerCallSite:
    """H3 (2026-09-11): site_planner.py's two `SITE-PLAN STOP` call sites
    (build_plan() and main()'s --detect-clusters branch) were the one known
    unmigrated FRESH-001 call site, confirmed live bootstrapping imaging/net
    knowledge (reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-
    prerequisites.md). Both now call
    freshness_guard.is_generation_allowed(mode="degraded") instead of a raw
    `kn.stale_since is not None` read. site_planner.py has no configure()
    seam of its own (unlike launch_gate.py/readiness_gate.py), so these
    tests prove the migration at the shared-function level it now actually
    calls -- the same behavioral-equivalence proof this file's other classes
    use, plus the CORRUPT-state case that is the actual point of this
    migration: the raw check could only ever express 2 states
    (stale_since None/set); this proves the new gate catches a 3rd real
    state the old code was structurally blind to."""

    def test_current_allowed_matches_old_no_stale_flag_behavior(self, tmp_path):
        _write_model(tmp_path, "imaging", "net", stale_since=None)
        allowed, result = fg.is_generation_allowed("imaging", "net", mode="degraded")
        assert allowed is True
        assert result.state == "CURRENT"

    def test_stale_blocked_matches_old_stale_flag_behavior(self, tmp_path):
        _write_model(tmp_path, "imaging", "net", stale_since="2026-08-14")
        allowed, result = fg.is_generation_allowed("imaging", "net", mode="degraded")
        assert allowed is False
        assert result.state == "STALE"

    def test_corrupt_state_blocked_even_though_stale_since_is_null(self, tmp_path):
        """The concrete proof this migration exists for: a knowledge bundle
        whose durable sources DISAGREE (real content drift or a corrupted
        baseline) but whose stale_since happens to still be null -- the OLD
        raw `stale_since is not None` check would have said "proceed", a
        silent false pass. The migrated gate correctly blocks it as
        CORRUPT."""
        _write_model(tmp_path, "imaging", "net", repo_sha="sha-model", stale_since=None)
        _write_upstream_baselines(tmp_path, {"imaging/net": "sha-DIFFERENT-from-model"})
        allowed, result = fg.is_generation_allowed("imaging", "net", mode="degraded")
        assert allowed is False
        assert result.state == "CORRUPT"
