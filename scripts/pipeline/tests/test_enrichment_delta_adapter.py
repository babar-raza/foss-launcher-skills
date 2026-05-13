"""Tests for TC-CE-024: delta_adapter.py — knowledge delta adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def repo_tree(tmp_path):
    """Create a minimal repo with content, knowledge, and enrichment artifacts."""
    # Content file
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "font" / "python" / "developer-guide"
    content_dir.mkdir(parents=True)
    page = content_dir / "core-management.md"
    page.write_text(
        "---\ntitle: Core Management\nevidence:\n  model_sha: abc123\n"
        "  claims:\n    - CLM-font-old1\n  apis:\n    - FontLoader\n---\n\nBody.\n",
        encoding="utf-8",
    )

    # Knowledge artifacts
    knowledge_dir = tmp_path / "knowledge" / "font" / "python" / "merged"
    knowledge_dir.mkdir(parents=True)

    (knowledge_dir / "knowledge_delta.json").write_text(json.dumps({
        "new_claims": ["CLM-font-new1", "CLM-font-new2"],
        "removed_claims": [],
        "modified_claims": [],
        "new_apis": ["FontInfo.weight"],
        "removed_apis": [],
    }), encoding="utf-8")

    (knowledge_dir / "claims.json").write_text(json.dumps([
        {"claim_id": "CLM-font-old1", "text": "Old claim"},
        {"claim_id": "CLM-font-new1", "text": "New claim 1"},
        {"claim_id": "CLM-font-new2", "text": "New claim 2"},
    ]), encoding="utf-8")

    # Enrichment reports
    report_dir = tmp_path / "reports" / "enrichment" / "font" / "python"
    report_dir.mkdir(parents=True)

    return tmp_path


def _import_adapter():
    from enrichment.delta_adapter import resolve_target_file, build_delta, write_delta
    return resolve_target_file, build_delta, write_delta


class TestResolveTargetFile:
    def test_resolves_docs_core_management(self, repo_tree):
        resolve_target_file, _, _ = _import_adapter()
        candidate = {"cluster": "core-management", "subdomain": "docs.aspose.org"}

        result = resolve_target_file(candidate, "font", "python", repo_root=repo_tree)
        assert result is not None
        assert "core-management.md" in result

    def test_returns_none_for_unknown_cluster(self, repo_tree):
        resolve_target_file, _, _ = _import_adapter()
        candidate = {"cluster": "nonexistent-cluster", "subdomain": "docs.aspose.org"}

        result = resolve_target_file(candidate, "font", "python", repo_root=repo_tree)
        assert result is None

    def test_returns_none_for_unknown_subdomain(self, repo_tree):
        resolve_target_file, _, _ = _import_adapter()
        candidate = {"cluster": "core-management", "subdomain": "unknown.aspose.org"}

        result = resolve_target_file(candidate, "font", "python", repo_root=repo_tree)
        assert result is None


class TestBuildDelta:
    def test_basic_delta_structure(self, repo_tree):
        _, build_delta, _ = _import_adapter()
        candidate = {
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.99,
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        assert "error" not in delta
        assert delta["family"] == "font"
        assert delta["platform"] == "python"
        assert "core-management.md" in delta["target_file"]
        assert delta["adapter_version"] == "1.0"

    def test_delta_contains_claims(self, repo_tree):
        _, build_delta, _ = _import_adapter()
        candidate = {
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.99,
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        assert "CLM-font-new1" in delta["delta"]["new_claims"]
        assert "CLM-font-new2" in delta["delta"]["new_claims"]
        assert delta["delta"]["removed_claims"] == []

    def test_delta_contains_page_context(self, repo_tree):
        _, build_delta, _ = _import_adapter()
        candidate = {
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.99,
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        assert "CLM-font-old1" in delta["page_context"]["current_claims"]
        assert delta["page_context"]["model_sha"] == "abc123"

    def test_delta_contains_provenance(self, repo_tree):
        _, build_delta, _ = _import_adapter()
        candidate = {
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.99,
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        assert "knowledge_delta_sha" in delta["provenance"]
        assert "adapter_run_id" in delta["provenance"]
        assert delta["provenance"]["adapter_run_id"].startswith("delta-adapt-")

    def test_error_when_target_not_resolved(self, repo_tree):
        _, build_delta, _ = _import_adapter()
        candidate = {
            "cluster": "nonexistent",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.5,
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        assert delta["error"] == "target_not_resolved"

    def test_feature_gap_included_when_present(self, repo_tree):
        _, build_delta, _ = _import_adapter()
        candidate = {
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.99,
            "feature_group": "variable-fonts",
            "uncovered_apis": ["VariationAxis"],
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        assert delta["feature_gap"] is not None
        assert delta["feature_gap"]["feature_group"] == "variable-fonts"


class TestWriteDelta:
    def test_writes_to_correct_path(self, repo_tree):
        _, build_delta, write_delta = _import_adapter()
        candidate = {
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "action": "update_existing_docs_page",
            "score": 0.99,
        }

        delta = build_delta(candidate, "font", "python", repo_root=repo_tree)
        out_path = write_delta(delta, "font", "python", repo_root=repo_tree)

        assert out_path.exists()
        assert "delta-adapt" in str(out_path)
        content = json.loads(out_path.read_text())
        assert content["family"] == "font"
