"""
Tests for scripts/pipeline/commands/knowledge/scan_stale.py.

Min required: 6 tests. This file has 8.
"""

import pytest
import yaml
from pathlib import Path

import commands.knowledge.scan_stale as ss


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_config():
    yield
    ss.configure(knowledge_root="knowledge")


def _make_model_yaml(knowledge_root: Path, family: str, platform: str, stale_since=None) -> Path:
    """Create a knowledge/{family}/{platform}/merged/model.yaml with optional stale_since."""
    merged = knowledge_root / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    data: dict = {"repo_sha": "abc123", "enrichment_status": "full"}
    if stale_since is not None:
        data["stale_since"] = stale_since
    p = merged / "model.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────


def test_stale_product_found(tmp_path):
    """Product with stale_since set is returned as stale."""
    kr = tmp_path / "knowledge"
    _make_model_yaml(kr, "pdf", "net", stale_since="2026-06-24")

    results = ss.find_stale_products(knowledge_root=str(kr))
    assert len(results) == 1
    assert results[0]["family"] == "pdf"
    assert results[0]["platform"] == "net"
    assert results[0]["stale_since"] == "2026-06-24"


def test_fresh_product_not_returned(tmp_path):
    """Product without stale_since (null) is NOT returned."""
    kr = tmp_path / "knowledge"
    _make_model_yaml(kr, "pdf", "net", stale_since=None)

    results = ss.find_stale_products(knowledge_root=str(kr))
    assert results == []


def test_multiple_products_mixed(tmp_path):
    """Only stale products are returned when mixed with fresh ones."""
    kr = tmp_path / "knowledge"
    _make_model_yaml(kr, "pdf", "net", stale_since="2026-06-24")
    _make_model_yaml(kr, "3d", "net", stale_since=None)
    _make_model_yaml(kr, "3d", "java", stale_since="2026-06-25")

    results = ss.find_stale_products(knowledge_root=str(kr))
    assert len(results) == 2
    families = {(r["family"], r["platform"]) for r in results}
    assert ("pdf", "net") in families
    assert ("3d", "java") in families
    assert ("3d", "net") not in families


def test_empty_knowledge_root_returns_empty(tmp_path):
    """Empty knowledge root with no model.yaml files returns empty list."""
    kr = tmp_path / "knowledge"
    kr.mkdir()

    results = ss.find_stale_products(knowledge_root=str(kr))
    assert results == []


def test_stale_since_empty_string_not_stale(tmp_path):
    """stale_since set to empty string is NOT treated as stale."""
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "net" / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text(yaml.dump({"stale_since": ""}), encoding="utf-8")

    results = ss.find_stale_products(knowledge_root=str(kr))
    assert results == []


def test_output_schema_has_required_fields(tmp_path):
    """Each stale product entry has family, platform, stale_since, model_yaml fields."""
    kr = tmp_path / "knowledge"
    _make_model_yaml(kr, "pdf", "net", stale_since="2026-06-24")

    results = ss.find_stale_products(knowledge_root=str(kr))
    assert len(results) == 1
    entry = results[0]
    assert "family" in entry
    assert "platform" in entry
    assert "stale_since" in entry
    assert "model_yaml" in entry
    assert "pdf/net" in entry["model_yaml"].replace("\\", "/")


def test_configure_overrides_knowledge_root(tmp_path):
    """configure() sets the knowledge root used by find_stale_products()."""
    kr = tmp_path / "knowledge"
    _make_model_yaml(kr, "cells", "java", stale_since="2026-06-20")

    ss.configure(knowledge_root=str(kr))
    # Call without explicit knowledge_root arg to use configured value
    results = ss.find_stale_products()
    assert len(results) == 1
    assert results[0]["family"] == "cells"


def test_malformed_yaml_skipped(tmp_path):
    """Model YAML files that can't be parsed are silently skipped."""
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "net" / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text("{{broken: yaml:", encoding="utf-8")

    # Should not raise; just returns empty
    results = ss.find_stale_products(knowledge_root=str(kr))
    assert results == []
