"""Shared test fixtures for foss-launcher-skills.

Provides reusable fixtures for evidence pipeline, knowledge pipeline,
and config tests. Import these by placing tests in the tests/ directory;
pytest discovers conftest.py automatically.
"""
import json
import os
import sys
from pathlib import Path

import yaml
import pytest

# Ensure scripts/ is importable for all tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# Safety guard — prevent tests from writing to aspose.org content
# ---------------------------------------------------------------------------

_FORBIDDEN_CONTENT_PATH_FRAGMENTS = (
    "aspose.org",
    "D:/onedrive/Documents/GitHub/aspose.org",
    "D:\\onedrive\\Documents\\GitHub\\aspose.org",
)


def pytest_configure(config):
    """Abort the test session if CONTENT_REPO_PATH points to aspose.org content."""
    content_repo = os.environ.get("CONTENT_REPO_PATH", "")
    if content_repo:
        normalized = content_repo.replace("\\", "/").lower()
        for fragment in _FORBIDDEN_CONTENT_PATH_FRAGMENTS:
            if fragment.replace("\\", "/").lower() in normalized:
                pytest.exit(
                    f"\n\nSAFETY ABORT: CONTENT_REPO_PATH='{content_repo}' points to "
                    f"aspose.org.\nTests must not run against production content.\n"
                    f"Set CONTENT_REPO_PATH to a sandbox/test directory instead.\n",
                    returncode=3,
                )


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_config(tmp_path):
    """Valid config.yaml with all required keys, data_root pointing to tmp_path."""
    config = {
        "content_repo": "",
        "sites": {
            "docs": {"content_path": "content/docs.aspose.org/en/{family}/{platform}/", "type": "docs"},
            "blog": {"content_path": "content/blog.aspose.org/{family}/{platform}/", "type": "blog"},
            "kb": {"content_path": "content/kb.aspose.org/en/{family}/{platform}/", "type": "kb"},
            "products": {"content_path": "content/products.aspose.org/en/{family}/", "type": "products"},
            "reference": {"content_path": "content/reference.aspose.org/en/{family}/{platform}/", "type": "reference"},
        },
        "knowledge_path": "knowledge/{family}/{platform}/",
        "evidence_path": "evidence/{family}/{platform}/",
        "reports_path": "reports/",
        "forbidden_paths": ["themes/", "layouts/", "configs/"],
        "governance": {
            "default_role": "writer",
            "roles": {
                "scout": {"skills": ["S-34"], "write_paths": ["knowledge/", "evidence/"]},
                "writer": {"skills": ["S-10"], "required_gates": ["S-01"], "write_paths": ["content/"]},
            },
            "session_limits": {"max_pages_per_session": 20, "max_families_per_session": 3, "max_consecutive_fails": 3},
            "audit": {"log_path": "reports/agents/"},
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return {"path": config_path, "data": config, "root": tmp_path}


# ---------------------------------------------------------------------------
# PEF / Evidence fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_pef():
    """Valid PEF dict for evidence pipeline tests."""
    return {
        "schema_version": 1,
        "family": "words",
        "platform": "python",
        "display_name": "Aspose.Words",
        "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": "abc123def456",
        "provenance_summary": {
            "dual": 2, "dual_fuzzy": 0, "scout_only": 1,
            "external_only": 0, "total": 3, "dual_pct": 66.7,
        },
        "api_confidence": "high",
        "claims": [
            {"claim_id": "CLM-001", "kind": "api_class", "text": "Document class", "confidence": 0.9, "provenance": "dual"},
            {"claim_id": "CLM-002", "kind": "api_method", "text": "Document.load", "confidence": 0.95, "provenance": "dual"},
            {"claim_id": "CLM-003", "kind": "api_method", "text": "Document.save", "confidence": 0.9, "provenance": "scout_only"},
        ],
        "api_surface": [
            {"name": "Document", "kind": "class", "methods": [
                {"name": "load"}, {"name": "save"}, {"name": "convert"},
            ]},
        ],
        "formats": [
            {"format": "DOCX", "can_import": True, "can_export": True, "direction": "both"},
            {"format": "PDF", "can_import": False, "can_export": True, "direction": "export"},
        ],
        "class_graph": [],
        "coverage_matrix": [],
        "constants": [],
        "limitations": [],
        "install": {"command": "pip install aspose-words-foss", "version": "1.0.0", "raw_md": ""},
        "snippets": [],
        "forbidden_claims": ["supports Workbook.protect"],
        "index_metadata": {},
    }


@pytest.fixture
def evidence_tree(tmp_path, sample_pef):
    """Full evidence/{family}/{platform}/ tree with pef.json."""
    evidence_dir = tmp_path / "evidence" / "words" / "python"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "pef.json").write_text(json.dumps(sample_pef), encoding="utf-8")
    (evidence_dir / "verification").mkdir()
    (evidence_dir / "diffs").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Knowledge fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def knowledge_tree(tmp_path):
    """Full knowledge/{family}/{platform}/merged/ tree with sample data."""
    merged = tmp_path / "knowledge" / "words" / "python" / "merged"
    merged.mkdir(parents=True)

    model = {
        "family": "words",
        "platform": "python",
        "repo_sha": "abc123def456",
        "merged_at": "2026-01-01T00:00:00+00:00",
        "version": "1.0.0",
        "install_command": "pip install aspose-words-foss",
        "stats": {"class_count": 1, "method_count": 3, "claim_count": 5},
    }
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")

    claims = [
        {"claim_id": "c1", "kind": "api_class", "text": "Document class", "confidence": 0.9, "provenance": "scout_only"},
        {"claim_id": "c2", "kind": "api_method", "text": "Document.load", "confidence": 0.95, "provenance": "dual"},
        {"claim_id": "c3", "kind": "api_method", "text": "Document.save", "confidence": 0.9, "provenance": "dual"},
        {"claim_id": "c4", "kind": "api_method", "text": "Document.convert", "confidence": 0.85, "provenance": "scout_only"},
        {"claim_id": "c5", "kind": "format_support", "text": "Supports DOCX", "confidence": 0.9, "provenance": "dual"},
    ]
    (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")

    api = [{"name": "Document", "kind": "class", "methods": [
        {"name": "load"}, {"name": "save"}, {"name": "convert"},
    ]}]
    (merged / "api_surface.json").write_text(json.dumps(api), encoding="utf-8")

    formats = [{"format": "DOCX", "can_import": True, "can_export": True, "direction": "both"}]
    (merged / "formats.json").write_text(json.dumps(formats), encoding="utf-8")

    (merged / "class_graph.json").write_text("[]", encoding="utf-8")
    (merged / "coverage_matrix.json").write_text("[]", encoding="utf-8")

    return tmp_path
