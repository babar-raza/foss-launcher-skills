"""Unit tests for check_proof_bundles.py using temp directories."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks" 
_PIPELINE_ROOT = _CI_ROOT.parent / "pipeline"
for _p in (_CI_ROOT, str(_PIPELINE_ROOT)):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import check_proof_bundles  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_obs(comp_dir: Path, name: str = "test-obs") -> Path:
    comp_dir.mkdir(parents=True, exist_ok=True)
    obs = comp_dir / f"{name}.md"
    obs.write_text(f"# {name}\n", encoding="utf-8")
    return obs


def _make_valid_bundle(proofs_dir: Path, obs_name: str) -> Path:
    bundle_dir = proofs_dir / f"{obs_name}-bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "bundle_id": f"test-{obs_name}",
        "created_at": "2026-03-31T00:00:00Z",
        "repo_sha": "abc123",
        "related_observation": f"{obs_name}.md",
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle_dir / "commands.log").write_text("echo test\n", encoding="utf-8")
    return bundle_dir


def _patch(monkeypatch, tmp_path):
    """Patch directory constants so file I/O goes to tmp_path instead of the real reports/ directory."""
    comp_dir = tmp_path / "compliance"
    proofs_dir = tmp_path / "proofs"
    monkeypatch.setattr(check_proof_bundles, "_COMPLIANCE_DIR", comp_dir)
    monkeypatch.setattr(check_proof_bundles, "_PROOFS_DIR", proofs_dir)
    monkeypatch.setattr(check_proof_bundles, "_INDEX_FILE", proofs_dir / "INDEX.json")
    return comp_dir, proofs_dir


# ---------------------------------------------------------------------------
# TestNoComplianceDir
# ---------------------------------------------------------------------------

class TestNoComplianceDir:
    def test_missing_compliance_dir_exits_0(self, tmp_path, monkeypatch):
        _patch(monkeypatch, tmp_path)
        # compliance dir does not exist
        assert check_proof_bundles.main([]) == 0

    def test_empty_compliance_dir_exits_0(self, tmp_path, monkeypatch):
        comp_dir, _ = _patch(monkeypatch, tmp_path)
        comp_dir.mkdir()
        assert check_proof_bundles.main([]) == 0


# ---------------------------------------------------------------------------
# TestValidBundle
# ---------------------------------------------------------------------------

class TestValidBundle:
    def test_observation_with_valid_bundle_exits_0(self, tmp_path, monkeypatch):
        comp_dir, proofs_dir = _patch(monkeypatch, tmp_path)
        _make_obs(comp_dir, "test-obs")
        _make_valid_bundle(proofs_dir, "test-obs")
        assert check_proof_bundles.main([]) == 0

    def test_valid_bundle_with_strict_still_exits_0(self, tmp_path, monkeypatch):
        comp_dir, proofs_dir = _patch(monkeypatch, tmp_path)
        _make_obs(comp_dir, "test-obs")
        _make_valid_bundle(proofs_dir, "test-obs")
        assert check_proof_bundles.main(["--strict"]) == 0


# ---------------------------------------------------------------------------
# TestMissingBundle
# ---------------------------------------------------------------------------

class TestMissingBundle:
    def test_missing_bundle_default_exits_0_advisory(self, tmp_path, monkeypatch):
        """Default mode: missing bundle is warning only, not failure."""
        comp_dir, proofs_dir = _patch(monkeypatch, tmp_path)
        _make_obs(comp_dir, "unmatched-obs")
        proofs_dir.mkdir()
        assert check_proof_bundles.main([]) == 0  # advisory — warning only

    def test_missing_bundle_strict_exits_1(self, tmp_path, monkeypatch):
        comp_dir, proofs_dir = _patch(monkeypatch, tmp_path)
        _make_obs(comp_dir, "unmatched-obs")
        proofs_dir.mkdir()
        assert check_proof_bundles.main(["--strict"]) == 1


# ---------------------------------------------------------------------------
# TestInvalidBundle
# ---------------------------------------------------------------------------

class TestInvalidBundle:
    def test_invalid_bundle_strict_exits_1(self, tmp_path, monkeypatch):
        """Bundle exists but manifest is missing required fields and commands.log."""
        comp_dir, proofs_dir = _patch(monkeypatch, tmp_path)
        _make_obs(comp_dir, "bad-obs")

        # Create a bundle directory that matches by name but has incomplete manifest
        bundle_dir = proofs_dir / "bad-obs"
        bundle_dir.mkdir(parents=True)
        # manifest present but missing 'created_at', 'repo_sha', and no commands.log
        (bundle_dir / "manifest.json").write_text(
            json.dumps({"bundle_id": "bad-obs"}), encoding="utf-8"
        )
        # commands.log intentionally absent

        assert check_proof_bundles.main(["--strict"]) == 1
