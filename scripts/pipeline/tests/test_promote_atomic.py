"""Tests for promote.py's promote_atomic() — staged-then-swap atomic promotion.

Reuses the scout/ fixture pattern from test_promote_integration.py. The global
autouse `_isolate_knowledge_state_globally` fixture (conftest.py) keeps
rebuild_one()'s knowledge_state writes off the real repo's data/ files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

# sys.path is set by tests/conftest.py — no manual insert needed here.
import promote as promote_mod

SCOUT_CLAIMS = [
    {"claim_id": "CLM-atomic-001", "text": "Scene.open(filename) loads a file.", "kind": "api_method"},
]
API_SURFACE = [
    {"name": "Scene", "methods": [{"name": "open", "return_type": "Scene", "params": ["filename"]}],
     "properties": [], "enum_members": [], "bases": []},
]


def _setup_scout(tmp_path: Path, *, repo_sha: str = "abc123def456") -> Path:
    knowledge_root = tmp_path / "knowledge"
    scout_dir = knowledge_root / "test" / "python" / "scout"
    scout_dir.mkdir(parents=True, exist_ok=True)
    (scout_dir / "claims.json").write_text(json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8")
    (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE, indent=2), encoding="utf-8")
    (scout_dir / "model.yaml").write_text(
        yaml.dump({"repo_sha": repo_sha, "product_name": "Test"}, default_flow_style=False),
        encoding="utf-8",
    )
    return knowledge_root


class TestPromoteAtomicHappyPath:
    def test_returns_true_and_writes_complete_bundle(self, tmp_path):
        kr = _setup_scout(tmp_path)
        result = promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        assert result is True
        merged = kr / "test" / "python" / "merged"
        manifest = json.loads((merged / "bundle_manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "COMPLETE"
        assert manifest["repo_sha"] == "abc123def456"

    def test_no_staging_or_bak_left_behind_on_success(self, tmp_path):
        kr = _setup_scout(tmp_path)
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        product = kr / "test" / "python"
        assert not (product / "merged.atomic-bak").exists()
        assert not list(product.glob("merged.staging.*"))
        assert (product / "merged").is_dir()

    def test_formats_md_and_api_surface_md_carry_bundle_id(self, tmp_path):
        kr = _setup_scout(tmp_path)
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        merged = kr / "test" / "python" / "merged"
        model = yaml.safe_load((merged / "model.yaml").read_text(encoding="utf-8"))
        api_md = (merged / "api_surface.md").read_text(encoding="utf-8")
        assert f"bundle_id: {model['bundle_id']}" in api_md

    def test_second_run_updates_merged_in_place_and_stays_healthy(self, tmp_path):
        kr = _setup_scout(tmp_path, repo_sha="sha-one")
        assert promote_mod.promote_atomic("test", "python", knowledge_root=str(kr)) is True
        # simulate a real refresh: scout advances to a new commit
        _setup_scout(tmp_path, repo_sha="sha-two")
        assert promote_mod.promote_atomic("test", "python", knowledge_root=str(kr)) is True
        merged = kr / "test" / "python" / "merged"
        model = yaml.safe_load((merged / "model.yaml").read_text(encoding="utf-8"))
        assert model["repo_sha"] == "sha-two"
        product = kr / "test" / "python"
        assert not (product / "merged.atomic-bak").exists()
        assert not list(product.glob("merged.staging.*"))

    def test_prior_repo_sha_visible_to_baseline_ledger_across_runs(self, tmp_path):
        """RPR-C-02's prior-repo_sha capture must still see real prior state even
        though promote() now writes into a staging copy, not the real merged/ —
        proves the "seed staging with a copy of current merged/" design works."""
        kr = _setup_scout(tmp_path, repo_sha="sha-one")
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        _setup_scout(tmp_path, repo_sha="sha-two")
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        ledger_path = kr / "test" / "python" / "merged" / "baseline_ledger.jsonl"
        lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        second_entry = json.loads(lines[-1])
        assert second_entry["prior_repo_sha"] == "sha-one"
        assert second_entry["new_repo_sha"] == "sha-two"


class TestPromoteAtomicFailureIsolation:
    def test_validation_failure_leaves_real_merged_untouched(self, tmp_path, monkeypatch):
        kr = _setup_scout(tmp_path, repo_sha="sha-good")
        assert promote_mod.promote_atomic("test", "python", knowledge_root=str(kr)) is True
        merged = kr / "test" / "python" / "merged"
        before = (merged / "model.yaml").read_text(encoding="utf-8")

        # Now make the NEXT promotion fail validation deterministically.
        _setup_scout(tmp_path, repo_sha="sha-bad")

        def _boom(*a, **kw):
            raise promote_mod.PromotionValidationError("synthetic failure for test")

        monkeypatch.setattr(promote_mod, "validate_promoted_artifacts", _boom)
        with pytest.raises(promote_mod.PromotionValidationError):
            promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))

        # real merged/ must be exactly as it was before the failed attempt
        after = (merged / "model.yaml").read_text(encoding="utf-8")
        assert after == before
        product = kr / "test" / "python"
        assert not list(product.glob("merged.staging.*")), "staging dir must be discarded on failure"
        assert not (product / "merged.atomic-bak").exists()

    def test_promote_returning_false_leaves_real_merged_untouched(self, tmp_path, monkeypatch):
        kr = _setup_scout(tmp_path, repo_sha="sha-good")
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        merged = kr / "test" / "python" / "merged"
        before = (merged / "model.yaml").read_text(encoding="utf-8")

        original_promote = promote_mod.promote

        def _fake_promote(*a, **kw):
            return False

        monkeypatch.setattr(promote_mod, "promote", _fake_promote)
        result = promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        assert result is False
        after = (merged / "model.yaml").read_text(encoding="utf-8")
        assert after == before
        assert not list((kr / "test" / "python").glob("merged.staging.*"))


class TestPromoteAtomicRecoveryIntegration:
    def test_stale_staging_from_prior_crash_is_cleaned_up_before_new_run(self, tmp_path):
        kr = _setup_scout(tmp_path, repo_sha="sha-one")
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        product = kr / "test" / "python"
        stale_staging = product / "merged.staging.leftover-from-a-crash"
        stale_staging.mkdir()
        (stale_staging / "partial.json").write_text("{}", encoding="utf-8")

        _setup_scout(tmp_path, repo_sha="sha-two")
        result = promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        assert result is True
        assert not stale_staging.exists()

    def test_refuses_new_swap_when_bak_and_staging_both_present_ambiguous(self, tmp_path):
        kr = _setup_scout(tmp_path, repo_sha="sha-one")
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        product = kr / "test" / "python"
        (product / "merged.atomic-bak").mkdir()
        (product / "merged.atomic-bak" / "bundle_manifest.json").write_text(
            json.dumps({"status": "COMPLETE"}), encoding="utf-8")
        (product / "merged.staging.orphan").mkdir()

        result = promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        assert result is False
        # nothing was touched -- AMBIGUOUS refuses to guess
        assert (product / "merged.atomic-bak").is_dir()
        assert (product / "merged.staging.orphan").is_dir()

    def test_recovers_from_prior_interrupted_swap_state_b(self, tmp_path):
        """merged/ absent, merged.atomic-bak/ present (as if a crash happened between the
        two renames of a prior swap) -- promote_atomic must self-heal via
        promote_recover before attempting a new promotion."""
        kr = _setup_scout(tmp_path, repo_sha="sha-one")
        promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        product = kr / "test" / "python"
        real_merged = product / "merged"
        bak = product / "merged.atomic-bak"
        real_merged.rename(bak)  # simulate: crashed after step 2, before step 3

        _setup_scout(tmp_path, repo_sha="sha-two")
        result = promote_mod.promote_atomic("test", "python", knowledge_root=str(kr))
        assert result is True
        assert not bak.exists()
        model = yaml.safe_load((product / "merged" / "model.yaml").read_text(encoding="utf-8"))
        assert model["repo_sha"] == "sha-two"
