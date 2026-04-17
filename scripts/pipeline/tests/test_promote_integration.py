"""Integration tests for promote.py — full scout/ -> merged/ pipeline.

Covers the gaps not addressed by test_merge_determinism.py:
- api_surface.json is correctly promoted from scout/ to merged/
- model.yaml is written to merged/ with stale_since: null
- All scout claims land in merged/ with provenance="scout"
- merged/claims.json claim count matches scout input
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# sys.path is set by tests/conftest.py — no manual insert needed here.
import promote as promote_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCOUT_CLAIMS = [
    {"claim_id": "CLM-test-p1-001", "text": "Scene.open(filename) loads a 3D file.", "kind": "api_method"},
    {"claim_id": "CLM-test-p1-002", "text": "Scene.save(filename) writes a 3D file.", "kind": "api_method"},
    {"claim_id": "CLM-test-p1-003", "text": "FileFormat.OBJ is a supported format.", "kind": "format"},
    {"claim_id": "CLM-test-p1-004", "text": "Node.name is the node identifier property.", "kind": "api_property"},
    {"claim_id": "CLM-test-p1-005", "text": "AssetInfo.title is the scene title.", "kind": "api_property"},
]

API_SURFACE = [
    {
        "name": "Scene",
        "methods": [
            {"name": "open", "return_type": "Scene", "params": ["filename"]},
            {"name": "save", "return_type": "", "params": ["filename"]},
        ],
        "properties": [{"name": "root_node", "type": "Node", "line": 10}],
        "enum_members": [],
        "bases": [],
    },
    {
        "name": "Node",
        "methods": [{"name": "create_child_node", "return_type": "Node", "params": []}],
        "properties": [{"name": "name", "type": "str", "line": 5}],
        "enum_members": [],
        "bases": [],
    },
    {
        "name": "FileFormat",
        "methods": [],
        "properties": [],
        "enum_members": [{"name": "OBJ", "value": "0"}, {"name": "FBX", "value": "1"}],
        "bases": [],
    },
]

MODEL_YAML = {
    "family": "test",
    "platform": "python",
    "repo_sha": "abc123def456",
    "stale_since": None,
    "class_count": 3,
    "method_count": 3,
    "enum_count": 1,
    "claim_count": 5,
}


def _setup_scout(tmp_path: Path) -> Path:
    """Create a minimal but valid scout/ knowledge tree in tmp_path."""
    knowledge_root = tmp_path / "knowledge"
    scout_dir = knowledge_root / "test" / "python" / "scout"
    scout_dir.mkdir(parents=True)

    (scout_dir / "claims.json").write_text(
        json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8"
    )
    (scout_dir / "api_surface.json").write_text(
        json.dumps(API_SURFACE, indent=2), encoding="utf-8"
    )
    (scout_dir / "model.yaml").write_text(
        yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8"
    )
    return knowledge_root


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestPromoteFullPipeline:
    """End-to-end: scout/ -> merged/ with all expected outputs."""

    def test_promote_returns_true_on_success(self, tmp_path):
        kr = _setup_scout(tmp_path)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True, "promote() should return True on a valid scout tree"

    def test_merged_claims_json_exists(self, tmp_path):
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_claims = kr / "test" / "python" / "merged" / "claims.json"
        assert merged_claims.exists(), "merged/claims.json must be written by promote()"

    def test_all_scout_claims_present_in_merged(self, tmp_path):
        """Every claim from scout/claims.json must appear in merged/claims.json."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        claim_ids = {c["claim_id"] for c in claims}
        for original in SCOUT_CLAIMS:
            assert original["claim_id"] in claim_ids, (
                f"Scout claim '{original['claim_id']}' missing from merged/claims.json"
            )

    def test_scout_claims_have_provenance_scout(self, tmp_path):
        """All promoted scout claims must have provenance='scout'."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        scout_ids = {c["claim_id"] for c in SCOUT_CLAIMS}
        for claim in claims:
            if claim["claim_id"] in scout_ids:
                assert claim.get("provenance") == "scout", (
                    f"Scout claim '{claim['claim_id']}' should have provenance='scout', "
                    f"got '{claim.get('provenance')}'"
                )

    def test_merged_api_surface_json_exists(self, tmp_path):
        """promote() must copy/promote api_surface.json to merged/."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_api = kr / "test" / "python" / "merged" / "api_surface.json"
        assert merged_api.exists(), "merged/api_surface.json must be written by promote()"

    def test_merged_api_surface_contains_all_classes(self, tmp_path):
        """All classes from scout/api_surface.json must appear in merged/api_surface.json."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_api = kr / "test" / "python" / "merged" / "api_surface.json"
        data = json.loads(merged_api.read_text(encoding="utf-8"))
        assert isinstance(data, list), "merged/api_surface.json should be a list"
        class_names = {cls["name"] for cls in data}
        for original_cls in API_SURFACE:
            assert original_cls["name"] in class_names, (
                f"Class '{original_cls['name']}' missing from merged/api_surface.json"
            )

    def test_merged_model_yaml_exists(self, tmp_path):
        """promote() must write model.yaml to merged/."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_model = kr / "test" / "python" / "merged" / "model.yaml"
        assert merged_model.exists(), "merged/model.yaml must be written by promote()"

    def test_merged_model_has_stale_since_null(self, tmp_path):
        """merged/model.yaml must have stale_since: null after successful promotion."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_model = kr / "test" / "python" / "merged" / "model.yaml"
        model = yaml.safe_load(merged_model.read_text(encoding="utf-8"))
        assert model.get("stale_since") is None, (
            f"merged/model.yaml should have stale_since: null, got {model.get('stale_since')!r}"
        )

    def test_merged_claim_count_matches_scout(self, tmp_path):
        """merged/claims.json count must equal number of scout claims (no enriched)."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        assert len(claims) == len(SCOUT_CLAIMS), (
            f"Expected {len(SCOUT_CLAIMS)} claims in merged output, got {len(claims)}"
        )


class TestPromoteWithMissingScout:
    """promote() must fail gracefully when scout/ artifacts are absent."""

    def test_missing_claims_json_returns_false(self, tmp_path):
        """promote() must return False if scout/claims.json is absent."""
        kr = tmp_path / "knowledge"
        scout_dir = kr / "test" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        # No claims.json
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is False

    def test_fl_directory_presence_returns_false(self, tmp_path):
        """promote() must return False if fl/ directory exists (guard against old layout)."""
        kr = _setup_scout(tmp_path)
        fl_dir = kr / "test" / "python" / "fl"
        fl_dir.mkdir(parents=True)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is False
