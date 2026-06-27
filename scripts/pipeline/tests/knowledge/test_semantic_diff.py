"""
Tests for scripts/pipeline/commands/knowledge/semantic_diff.py (S-104).

Min required: 7 tests. This file has 9.
"""

import json
import pytest
from pathlib import Path

import commands.knowledge.semantic_diff as sd


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_config(tmp_path):
    """Reset module config and redirect paths to tmp_path after each test."""
    yield
    sd.configure(
        knowledge_root="knowledge",
        reports_root="reports/refresh_review",
    )


def _make_delta(
    tmp_path: Path,
    family: str,
    platform: str,
    new_apis=None,
    removed_apis=None,
    modified_apis=None,
    resurrected_apis=None,
    new_claims=None,
    removed_claims=None,
    modified_claims=None,
    base_sha="abc123",
    current_sha="def456",
):
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)
    delta = {
        "base_sha": base_sha,
        "current_sha": current_sha,
        "new_apis": new_apis or [],
        "removed_apis": removed_apis or [],
        "modified_apis": modified_apis or [],
        "resurrected_apis": resurrected_apis or [],
        "new_claims": new_claims or [],
        "removed_claims": removed_claims or [],
        "modified_claims": modified_claims or [],
    }
    (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")
    sd.configure(knowledge_root=str(tmp_path / "knowledge"), reports_root=str(tmp_path / "reports"))
    return delta


# ── Tests ─────────────────────────────────────────────────────────────────


def test_api_removed_classified_correctly(tmp_path):
    """Removed API class produces change_type=API_REMOVED with BODY_UPDATE impact."""
    _make_delta(tmp_path, "pdf", "net", removed_apis=["Document"])
    changes = sd.run("pdf", "net")
    assert len(changes) == 1
    c = changes[0]
    assert c["change_type"] == sd.API_REMOVED
    assert c["symbol"] == "Document"
    assert c["public_impact"] == sd.USER_VISIBLE
    assert c["content_impact"] == sd.BODY_UPDATE


def test_api_added_classified_correctly(tmp_path):
    """New API class produces change_type=API_ADDED with BODY_UPDATE impact."""
    _make_delta(tmp_path, "pdf", "net", new_apis=["PdfConverter"])
    changes = sd.run("pdf", "net")
    assert len(changes) == 1
    c = changes[0]
    assert c["change_type"] == sd.API_ADDED
    assert c["symbol"] == "PdfConverter"
    assert c["content_impact"] == sd.BODY_UPDATE


def test_modified_api_classified(tmp_path):
    """Modified API class produces change_type=API_MODIFIED."""
    _make_delta(tmp_path, "pdf", "net", modified_apis=["TextFragment"])
    changes = sd.run("pdf", "net")
    assert len(changes) == 1
    assert changes[0]["change_type"] == sd.API_MODIFIED
    assert changes[0]["symbol"] == "TextFragment"


def test_feature_removed_from_claims(tmp_path):
    """Removed claim produces change_type=FEATURE_REMOVED."""
    _make_delta(tmp_path, "pdf", "net", removed_claims=["CLM-pdf-abc123"])
    changes = sd.run("pdf", "net")
    assert len(changes) == 1
    c = changes[0]
    assert c["change_type"] == sd.FEATURE_REMOVED
    assert c["symbol_kind"] == "claim"
    assert c["content_impact"] == sd.BODY_UPDATE


def test_internal_change_not_user_visible(tmp_path):
    """Class matching 'Internal' pattern is classified as INTERNAL_ONLY."""
    _make_delta(tmp_path, "pdf", "net", modified_apis=["InternalSomething"])
    changes = sd.run("pdf", "net")
    assert len(changes) == 1
    c = changes[0]
    assert c["public_impact"] == sd.INTERNAL_ONLY
    assert c["content_impact"] == sd.NO_ACTION


def test_empty_delta_produces_empty_output(tmp_path):
    """Empty delta → empty changes list (no errors)."""
    _make_delta(tmp_path, "pdf", "net")
    changes = sd.run("pdf", "net")
    assert changes == []


def test_output_schema_valid(tmp_path):
    """Every change object contains all required fields with correct types."""
    _make_delta(tmp_path, "pdf", "net", removed_apis=["Doc"], new_claims=["CLM-pdf-x1"])
    changes = sd.run("pdf", "net")
    required_keys = {
        "change_id", "family", "platform", "base_sha", "current_sha",
        "evidence_paths", "change_type", "symbol", "symbol_kind",
        "public_impact", "content_impact", "confidence",
    }
    for c in changes:
        missing = required_keys - c.keys()
        assert not missing, f"Change missing keys: {missing}"
        assert isinstance(c["confidence"], float)
        assert 0.0 <= c["confidence"] <= 1.0
        assert isinstance(c["evidence_paths"], list)


def test_change_ids_are_unique(tmp_path):
    """All generated change_ids are unique within a run."""
    _make_delta(
        tmp_path, "pdf", "net",
        removed_apis=["A", "B"],
        new_apis=["C"],
        removed_claims=["CLM-pdf-x1", "CLM-pdf-x2"],
    )
    changes = sd.run("pdf", "net")
    ids = [c["change_id"] for c in changes]
    assert len(ids) == len(set(ids)), "Duplicate change_ids detected"


def test_output_written_to_expected_path(tmp_path):
    """Output JSON is written to reports_root/{family}/{platform}/semantic_changes.json."""
    _make_delta(tmp_path, "pdf", "net", new_apis=["NewClass"])
    changes = sd.run("pdf", "net")
    out_path = tmp_path / "reports" / "pdf" / "net" / "semantic_changes.json"
    assert out_path.exists(), "Output file not created"
    with open(out_path, encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded) == len(changes)
    assert loaded[0]["change_type"] == sd.API_ADDED
