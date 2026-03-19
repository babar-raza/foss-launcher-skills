"""Tests for scripts/mental_model.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import mental_model


def _make_pef(tmp_path, family="words", platform="python", methods=None, claims=None, formats=None):
    """Create a PEF file and return the evidence dir."""
    evidence_dir = tmp_path / "evidence" / family / platform
    evidence_dir.mkdir(parents=True)

    if methods is None:
        methods = [{"name": "load"}, {"name": "save"}, {"name": "convert"},
                   {"name": "merge"}, {"name": "split"}]
    if claims is None:
        claims = [
            {"claim_id": "c1", "kind": "api_class", "text": "Document class", "confidence": 0.9, "provenance": "dual"},
            {"claim_id": "c2", "kind": "api_method", "text": "Document.load", "confidence": 0.95, "provenance": "dual"},
            {"claim_id": "c3", "kind": "api_method", "text": "Document.save", "confidence": 0.9, "provenance": "scout_only"},
        ]
    if formats is None:
        formats = [
            {"format": "DOCX", "can_import": True, "can_export": True, "direction": "both"},
            {"format": "PDF", "can_import": False, "can_export": True, "direction": "export"},
        ]

    pef = {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "display_name": "Aspose.Words",
        "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": "abc123",
        "provenance_summary": {"dual": 2, "dual_fuzzy": 0, "scout_only": 1, "external_only": 0, "total": 3, "dual_pct": 66.7},
        "api_confidence": "high",
        "claims": claims,
        "api_surface": [{"name": "Document", "kind": "class", "methods": methods}],
        "formats": formats,
        "class_graph": [],
        "coverage_matrix": [],
        "constants": [],
        "limitations": [],
        "install": {"command": "pip install aspose-words-foss", "version": "1.0.0", "raw_md": ""},
        "snippets": [],
        "forbidden_claims": [],
        "index_metadata": {},
    }
    (evidence_dir / "pef.json").write_text(json.dumps(pef), encoding="utf-8")
    return evidence_dir


def test_tier_classification():
    api = [
        {"name": "BigClass", "kind": "class", "methods": [{"name": f"m{i}"} for i in range(8)]},
        {"name": "MedClass", "kind": "class", "methods": [{"name": "a"}, {"name": "b"}, {"name": "c"}]},
        {"name": "SmallClass", "kind": "class", "methods": [{"name": "x"}]},
    ]
    claims = [
        {"text": "BigClass does things", "provenance": "dual"},
        {"text": "MedClass helper", "provenance": "scout_only"},
    ]
    tiers = mental_model._classify_tiers(api, claims)
    assert len(tiers["tier_1_core"]) == 1
    assert tiers["tier_1_core"][0]["class"] == "BigClass"
    assert len(tiers["tier_2_supporting"]) == 1
    assert len(tiers["tier_3_utility"]) == 1


def test_build_mental_model(tmp_path, monkeypatch):
    _make_pef(tmp_path)
    monkeypatch.setattr(mental_model, "EVIDENCE_ROOT", tmp_path / "evidence")

    # Create some content pages
    content_root = tmp_path / "content"
    docs_dir = content_root / "docs.aspose.org" / "en" / "words" / "python"
    docs_dir.mkdir(parents=True)
    (docs_dir / "installation.md").write_text("# Installation\n", encoding="utf-8")

    model = mental_model.build_mental_model("words", "python", content_root=content_root)

    assert model is not None
    assert model["schema_version"] == 1
    assert model["family"] == "words"
    assert "capability_tiers" in model
    assert "gap_analysis" in model
    assert "readiness" in model


def test_gap_analysis_detects_missing_pages(tmp_path, monkeypatch):
    _make_pef(tmp_path)
    monkeypatch.setattr(mental_model, "EVIDENCE_ROOT", tmp_path / "evidence")

    # No content pages at all
    empty_content = tmp_path / "empty_content"
    empty_content.mkdir()
    model = mental_model.build_mental_model("words", "python", content_root=empty_content)

    gaps = model["gap_analysis"]
    assert "docs/installation" in gaps["missing_page_types"]
    assert "docs/quick-start" in gaps["missing_page_types"]
    assert "blog/intro" in gaps["missing_page_types"]


def test_readiness_blocked_when_low_confidence(tmp_path, monkeypatch):
    evidence_dir = tmp_path / "evidence" / "words" / "python"
    evidence_dir.mkdir(parents=True)

    pef = {
        "schema_version": 1, "family": "words", "platform": "python",
        "display_name": "Aspose.Words", "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": "abc", "api_confidence": "low",
        "provenance_summary": {"dual": 0, "dual_fuzzy": 0, "scout_only": 3, "external_only": 0, "total": 3, "dual_pct": 0},
        "claims": [{"claim_id": "c1", "kind": "api_class", "text": "Doc", "provenance": "scout_only"}],
        "api_surface": [{"name": "Doc", "kind": "class", "methods": []}],
        "formats": [], "class_graph": [], "coverage_matrix": [], "constants": [],
        "limitations": [], "install": {"command": "", "version": "", "raw_md": ""},
        "snippets": [], "forbidden_claims": [], "index_metadata": {},
    }
    (evidence_dir / "pef.json").write_text(json.dumps(pef), encoding="utf-8")
    monkeypatch.setattr(mental_model, "EVIDENCE_ROOT", tmp_path / "evidence")

    model = mental_model.build_mental_model("words", "python", content_root=tmp_path / "none")
    assert model["readiness"]["overall"] == "blocked"
    assert any("low" in b for b in model["readiness"]["blockers"])


def test_format_matrix(tmp_path, monkeypatch):
    _make_pef(tmp_path)
    monkeypatch.setattr(mental_model, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = mental_model.build_mental_model("words", "python", content_root=tmp_path / "none")

    fm = model["format_matrix"]
    assert any(f["format"] == "DOCX" for f in fm["import"])
    assert any(f["format"] == "PDF" for f in fm["export"])


def test_skip_missing_pef(tmp_path, monkeypatch):
    monkeypatch.setattr(mental_model, "EVIDENCE_ROOT", tmp_path / "evidence")
    result = mental_model.build_mental_model("nonexistent", "python")
    assert result is None
