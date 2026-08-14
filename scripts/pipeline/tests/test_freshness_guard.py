"""Tests for lib/freshness_guard.py — the single source of truth for knowledge
bundle freshness, its 8-state model, and the collapsed baseline resolution order."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
_LIB_DIR = _PIPELINE_DIR / "lib"
for p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import freshness_guard as fg


@pytest.fixture(autouse=True)
def _configure(tmp_path):
    fg.configure(repo_root=tmp_path)
    yield
    fg.configure(repo_root=None)


def _write_model(tmp_path, family, platform, *, repo_sha="sha-1", stale_since=None, schema_version=2):
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    model = {"repo_sha": repo_sha, "stale_since": stale_since, "schema_version": schema_version}
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
    return merged


def _write_bundle_manifest(merged_dir, *, status="COMPLETE"):
    (merged_dir / "bundle_manifest.json").write_text(
        json.dumps({"status": status, "bundle_id": "b1"}), encoding="utf-8")


def _write_products_json(tmp_path, family, platform, *, clone_url="https://example.com/repo.git"):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "products.json").write_text(
        json.dumps([{"family": family, "platform": platform, "clone_url": clone_url}]), encoding="utf-8")


def _write_upstream_baselines(tmp_path, entries: dict):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "upstream_baselines.json").write_text(json.dumps(entries), encoding="utf-8")


class TestResolveBaseline:
    def test_prefers_model_yaml_over_projections(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="from-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "from-projection"})
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-model" and source == "model.yaml"

    def test_falls_back_to_upstream_baselines_when_no_model(self, tmp_path):
        _write_upstream_baselines(tmp_path, {"cells/net": "from-projection"})
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-projection" and source == "upstream_baselines.json"

    def test_falls_back_to_knowledge_state_when_no_model_or_upstream_baselines(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "knowledge_state.json").write_text(
            json.dumps({"cells/net": {"accepted_baseline": {"repo_sha": "from-state"}}}), encoding="utf-8")
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-state" and source == "knowledge_state.json"

    def test_falls_back_to_ledger_head(self, tmp_path):
        merged = tmp_path / "knowledge" / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "baseline_ledger_head.json").write_text(
            json.dumps({"new_repo_sha": "from-ledger"}), encoding="utf-8")
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-ledger" and source == "baseline_ledger_head.json"

    def test_returns_none_when_nothing_resolves(self, tmp_path):
        # baseline_resolver._sample_content_model_sha's default discover_content_fn
        # is not repo-root-isolated (scans the REAL repo's content/ tree) — patch it
        # out explicitly so this test proves the "truly nothing resolves" floor,
        # not "the real repo happens to have committed evidence for cells/net".
        with patch("baseline_resolver._sample_content_model_sha", return_value=None):
            sha, source = fg.resolve_baseline("cells", "net")
        assert sha is None and source == "none"


class TestDurableSourcesAgree:
    def test_agree_when_only_one_source_present(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        agree, detail = fg._durable_sources_agree("cells", "net")
        assert agree is True

    def test_disagree_when_model_and_projection_differ(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-projection-DIFFERENT"})
        agree, detail = fg._durable_sources_agree("cells", "net")
        assert agree is False
        assert detail["model.yaml"] == "sha-model"
        assert detail["upstream_baselines.json"] == "sha-projection-DIFFERENT"

    def test_agree_when_all_sources_match(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-1"})
        agree, _ = fg._durable_sources_agree("cells", "net")
        assert agree is True


class TestCheckFreshnessStates:
    def test_provenance_missing_when_no_model_yaml(self, tmp_path):
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "PROVENANCE_MISSING"

    def test_current_in_degraded_mode_when_no_stale_flag(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since=None)
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CURRENT"

    def test_stale_in_degraded_mode_when_stale_since_set(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "STALE"

    def test_corrupt_when_durable_sources_disagree(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-DIFFERENT"})
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CORRUPT"

    def test_corrupt_when_bundle_manifest_status_not_complete(self, tmp_path):
        merged = _write_model(tmp_path, "cells", "net")
        _write_bundle_manifest(merged, status="IN_PROGRESS")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CORRUPT"

    def test_current_when_bundle_manifest_complete(self, tmp_path):
        merged = _write_model(tmp_path, "cells", "net")
        _write_bundle_manifest(merged, status="COMPLETE")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CURRENT"

    def test_refreshing_when_regen_lock_held(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        from knowledge_regen_lock import acquire_regen_lock
        lock = acquire_regen_lock("cells", "net", owner="test", knowledge_root=fg.KNOWLEDGE_ROOT)
        with lock:
            result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "REFRESHING"

    def test_refresh_failed_when_marker_present(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        fg.mark_regen_failed("cells", "net", reason="enrich.py timed out")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "REFRESH_FAILED"
        assert "enrich.py timed out" in result.reason

    def test_refresh_failed_cleared_by_mark_succeeded(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        fg.mark_regen_failed("cells", "net", reason="boom")
        fg.mark_regen_succeeded("cells", "net")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state != "REFRESH_FAILED"

    def test_offline_mode_never_touches_network_and_ignores_stale_flag(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        with patch.object(fg, "_live_upstream_sha") as mock_live:
            result = fg.check_freshness("cells", "net", mode="offline")
        mock_live.assert_not_called()
        assert result.state == "CURRENT"
        assert "offline" in result.reason

    def test_strict_mode_current_when_live_sha_matches(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value="sha-1"):
            result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "CURRENT"

    def test_strict_mode_stale_when_live_sha_differs(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-old")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value="sha-new"):
            result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "STALE"
        assert result.live_sha == "sha-new"

    def test_strict_mode_upstream_unavailable_never_downgrades_silently(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "UPSTREAM_UNAVAILABLE"

    def test_strict_mode_upstream_unavailable_when_no_repo_url(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        # no products.json at all
        result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "UPSTREAM_UNAVAILABLE"

    def test_invalid_mode_raises(self, tmp_path):
        with pytest.raises(ValueError):
            fg.check_freshness("cells", "net", mode="not-a-real-mode")


class TestIsGenerationAllowed:
    def test_allowed_true_for_current(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        allowed, result = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is True
        assert result.state == "CURRENT"

    def test_allowed_false_for_stale(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        allowed, result = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is False
        assert result.state == "STALE"

    def test_last_known_good_requires_explicit_opt_in(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            allowed, result = fg.is_generation_allowed(
                "cells", "net", mode="strict", allow_last_known_good=False)
        assert allowed is False
        assert result.state == "UPSTREAM_UNAVAILABLE"

    def test_last_known_good_allowed_when_opted_in_and_bundle_exists(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            allowed, result = fg.is_generation_allowed(
                "cells", "net", mode="strict", allow_last_known_good=True)
        assert allowed is True
        assert result.state == "LAST_KNOWN_GOOD"

    def test_last_known_good_is_audit_logged(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            fg.is_generation_allowed("cells", "net", mode="strict", allow_last_known_good=True)
        assert fg.LAST_KNOWN_GOOD_LOG.is_file()
        entry = json.loads(fg.LAST_KNOWN_GOOD_LOG.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["family"] == "cells" and entry["platform"] == "net"

    def test_last_known_good_not_allowed_without_prior_bundle(self, tmp_path):
        # no model.yaml at all -> PROVENANCE_MISSING, not eligible for LKG fallback
        allowed, result = fg.is_generation_allowed(
            "cells", "net", mode="strict", allow_last_known_good=True)
        assert allowed is False
        assert result.state == "PROVENANCE_MISSING"

    def test_corrupt_never_allowed_even_with_last_known_good(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-DIFFERENT"})
        allowed, result = fg.is_generation_allowed(
            "cells", "net", mode="degraded", allow_last_known_good=True)
        assert allowed is False
        assert result.state == "CORRUPT"
