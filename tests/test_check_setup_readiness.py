"""Tests for knowledge readiness gate in check_setup.py.

Verifies:
  1. Skeletal knowledge (< threshold claims) returns ERROR
  2. Sufficient knowledge returns OK
  3. Missing model.yaml returns ERROR (not the old WARN)
  4. Stale knowledge (stale_since set) returns ERROR
  5. Thresholds are configurable via config dict
"""
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_setup import OK, WARN, ERROR, check_setup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knowledge(
    tmp_path,
    family="words",
    platform="python",
    claims=100,
    classes=20,
    stale_since=None,
):
    """Write a minimal merged knowledge model to tmp_path/knowledge/."""
    merged_dir = tmp_path / "knowledge" / family / platform / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)

    model = {
        "family": family,
        "platform": platform,
        "source": "merged",
        "stale_since": stale_since,
        "stats": {
            "merged_claims": claims,
            "class_count": classes,
        },
    }
    (merged_dir / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
    (merged_dir / "index.json").write_text('{"products": []}', encoding="utf-8")


def _config(tmp_path, **overrides):
    cfg = {
        "content_repo": str(tmp_path),
        "sites": {"docs": {"content_path": "content/docs/{family}/{platform}/"}},
        "knowledge_root": str(tmp_path / "knowledge"),
        "reports_path": "reports",
    }
    cfg.update(overrides)
    return cfg


def _levels(issues):
    return [lvl for lvl, _ in issues]


def _msgs(issues):
    return [msg for _, msg in issues]


def _worst(issues):
    rank = {OK: 0, WARN: 1, ERROR: 2}
    return max((rank.get(lvl, 0) for lvl, _ in issues), default=0)


# ---------------------------------------------------------------------------
# Knowledge missing → ERROR
# ---------------------------------------------------------------------------

class TestMissingKnowledge:
    def test_missing_model_yaml_returns_error(self, tmp_path):
        config = _config(tmp_path)
        # No knowledge files created
        issues = check_setup(config, tmp_path, family="words", platform="python")
        assert _worst(issues) == 2
        knowledge_errors = [msg for lvl, msg in issues if lvl == ERROR and "model.yaml" in msg]
        assert len(knowledge_errors) >= 1

    def test_missing_index_json_returns_error(self, tmp_path):
        config = _config(tmp_path)
        # Create model.yaml but no index.json
        merged_dir = tmp_path / "knowledge" / "words" / "python" / "merged"
        merged_dir.mkdir(parents=True)
        model = {"stats": {"merged_claims": 100, "class_count": 20}}
        (merged_dir / "model.yaml").write_text(yaml.dump(model))

        issues = check_setup(config, tmp_path, family="words", platform="python")
        assert _worst(issues) == 2
        idx_errors = [msg for lvl, msg in issues if lvl == ERROR and "index.json" in msg]
        assert len(idx_errors) >= 1


# ---------------------------------------------------------------------------
# Skeletal knowledge → ERROR
# ---------------------------------------------------------------------------

class TestSkeletalKnowledge:
    def test_below_min_claims_returns_error(self, tmp_path):
        _make_knowledge(tmp_path, claims=5, classes=20)
        config = _config(tmp_path)

        issues = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=50, _min_classes=10,
        )
        claim_errors = [msg for lvl, msg in issues if lvl == ERROR and "claims" in msg]
        assert len(claim_errors) >= 1
        assert "5" in claim_errors[0]  # shows actual count
        assert "50" in claim_errors[0]  # shows threshold

    def test_below_min_classes_returns_error(self, tmp_path):
        _make_knowledge(tmp_path, claims=100, classes=3)
        config = _config(tmp_path)

        issues = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=50, _min_classes=10,
        )
        class_errors = [msg for lvl, msg in issues if lvl == ERROR and "classes" in msg]
        assert len(class_errors) >= 1

    def test_sufficient_knowledge_returns_ok(self, tmp_path):
        _make_knowledge(tmp_path, claims=200, classes=30)
        config = _config(tmp_path)

        issues = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=50, _min_classes=10,
        )
        # Should have no ERROR from knowledge
        knowledge_errors = [
            msg for lvl, msg in issues
            if lvl == ERROR and ("claims" in msg or "classes" in msg or "model.yaml" in msg)
        ]
        assert knowledge_errors == []

    def test_exactly_at_threshold_passes(self, tmp_path):
        _make_knowledge(tmp_path, claims=50, classes=10)
        config = _config(tmp_path)

        issues = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=50, _min_classes=10,
        )
        knowledge_errors = [
            msg for lvl, msg in issues
            if lvl == ERROR and ("claims" in msg or "classes" in msg)
        ]
        assert knowledge_errors == []


# ---------------------------------------------------------------------------
# Stale knowledge → ERROR
# ---------------------------------------------------------------------------

class TestStaleKnowledge:
    def test_stale_since_set_returns_error(self, tmp_path):
        _make_knowledge(tmp_path, claims=200, classes=30, stale_since="2026-03-15")
        config = _config(tmp_path)

        issues = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=50, _min_classes=10,
        )
        stale_errors = [msg for lvl, msg in issues if lvl == ERROR and "stale" in msg]
        assert len(stale_errors) >= 1
        assert "2026-03-15" in stale_errors[0]

    def test_stale_since_null_passes(self, tmp_path):
        _make_knowledge(tmp_path, claims=200, classes=30, stale_since=None)
        config = _config(tmp_path)

        issues = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=50, _min_classes=10,
        )
        stale_errors = [msg for lvl, msg in issues if lvl == ERROR and "stale" in msg]
        assert stale_errors == []


# ---------------------------------------------------------------------------
# Threshold configurability
# ---------------------------------------------------------------------------

class TestThresholds:
    def test_custom_thresholds_via_arguments(self, tmp_path):
        """_min_claims and _min_classes override defaults."""
        _make_knowledge(tmp_path, claims=10, classes=2)
        config = _config(tmp_path)

        # With low thresholds, should pass
        issues_low = check_setup(
            config, tmp_path, family="words", platform="python",
            _min_claims=5, _min_classes=1,
        )
        claim_errors = [msg for lvl, msg in issues_low if lvl == ERROR and "claims" in msg]
        assert claim_errors == []

    def test_custom_thresholds_via_config(self, tmp_path):
        """knowledge_readiness section in config.yaml sets thresholds."""
        _make_knowledge(tmp_path, claims=10, classes=2)
        config = _config(tmp_path)
        config["knowledge_readiness"] = {"min_claims": 5, "min_classes": 1}

        issues = check_setup(config, tmp_path, family="words", platform="python")
        claim_errors = [msg for lvl, msg in issues if lvl == ERROR and "claims" in msg]
        assert claim_errors == []

    def test_no_family_platform_skips_knowledge_check(self, tmp_path):
        """Without family/platform, no knowledge check is run."""
        config = _config(tmp_path)
        issues = check_setup(config, tmp_path)  # no family/platform
        knowledge_msgs = [msg for _, msg in issues if "knowledge" in msg.lower()]
        assert knowledge_msgs == []
