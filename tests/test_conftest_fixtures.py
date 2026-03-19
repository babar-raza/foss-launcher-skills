"""Tests that verify conftest.py shared fixtures are functional.

These tests ensure the fixtures produce valid, well-structured data
so that other test modules can rely on them safely.
"""
import json
from pathlib import Path

import yaml


def test_minimal_config_structure(minimal_config):
    """minimal_config fixture produces a valid config dict and file."""
    assert minimal_config["path"].exists()
    assert minimal_config["path"].name == "config.yaml"
    assert isinstance(minimal_config["data"], dict)
    assert isinstance(minimal_config["root"], Path)

    # Required keys present
    data = minimal_config["data"]
    for key in ("content_repo", "sites", "knowledge_path", "evidence_path",
                "forbidden_paths", "governance"):
        assert key in data, f"Missing required config key: {key}"

    # File on disk matches dict
    loaded = yaml.safe_load(minimal_config["path"].read_text(encoding="utf-8"))
    assert loaded["governance"]["default_role"] == data["governance"]["default_role"]


def test_minimal_config_sites(minimal_config):
    """Sites in minimal_config have content_path and type."""
    sites = minimal_config["data"]["sites"]
    assert len(sites) >= 3
    for name, site in sites.items():
        assert "content_path" in site, f"Site {name} missing content_path"
        assert "type" in site, f"Site {name} missing type"
        assert "{family}" in site["content_path"]


def test_sample_pef_structure(sample_pef):
    """sample_pef fixture produces a valid PEF dict."""
    assert sample_pef["schema_version"] == 1
    assert sample_pef["family"] == "words"
    assert sample_pef["platform"] == "python"

    # Required PEF sections
    for key in ("claims", "api_surface", "formats", "provenance_summary",
                "api_confidence", "install"):
        assert key in sample_pef, f"Missing PEF key: {key}"

    assert len(sample_pef["claims"]) >= 3
    assert len(sample_pef["api_surface"]) >= 1
    assert sample_pef["api_confidence"] in ("high", "medium", "low")

    # Claims have required fields
    for claim in sample_pef["claims"]:
        assert "claim_id" in claim
        assert "kind" in claim
        assert "provenance" in claim


def test_sample_pef_provenance_summary(sample_pef):
    """Provenance summary is internally consistent."""
    ps = sample_pef["provenance_summary"]
    assert ps["total"] == ps["dual"] + ps["dual_fuzzy"] + ps["scout_only"] + ps["external_only"]
    assert 0 <= ps["dual_pct"] <= 100


def test_evidence_tree_structure(evidence_tree):
    """evidence_tree fixture creates correct directory layout with pef.json."""
    root = evidence_tree
    pef_path = root / "evidence" / "words" / "python" / "pef.json"
    assert pef_path.exists()

    pef = json.loads(pef_path.read_text(encoding="utf-8"))
    assert pef["family"] == "words"
    assert pef["schema_version"] == 1

    # Subdirectories created
    assert (root / "evidence" / "words" / "python" / "verification").is_dir()
    assert (root / "evidence" / "words" / "python" / "diffs").is_dir()


def test_knowledge_tree_structure(knowledge_tree):
    """knowledge_tree fixture creates correct merged/ directory layout."""
    root = knowledge_tree
    merged = root / "knowledge" / "words" / "python" / "merged"
    assert merged.is_dir()

    # All required merged files exist
    for filename in ("model.yaml", "claims.json", "api_surface.json",
                     "formats.json", "class_graph.json", "coverage_matrix.json"):
        assert (merged / filename).exists(), f"Missing {filename} in knowledge_tree"

    # model.yaml is valid
    model = yaml.safe_load((merged / "model.yaml").read_text(encoding="utf-8"))
    assert model["family"] == "words"
    assert model["platform"] == "python"

    # claims.json has entries
    claims = json.loads((merged / "claims.json").read_text(encoding="utf-8"))
    assert len(claims) == 5
    assert all("claim_id" in c for c in claims)


def test_knowledge_tree_api_surface(knowledge_tree):
    """knowledge_tree api_surface.json has expected structure."""
    merged = knowledge_tree / "knowledge" / "words" / "python" / "merged"
    api = json.loads((merged / "api_surface.json").read_text(encoding="utf-8"))
    assert len(api) >= 1
    assert api[0]["name"] == "Document"
    assert len(api[0]["methods"]) >= 3
