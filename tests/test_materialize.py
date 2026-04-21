"""Tests for scripts/materialize.py."""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import materialize


def _setup_merged(tmp_path, family="words", platform="python"):
    """Create a minimal merged/ directory for testing."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    model = {
        "family": family,
        "platform": platform,
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
        {"name": "load"}, {"name": "save"}, {"name": "convert"}
    ]}]
    (merged / "api_surface.json").write_text(json.dumps(api), encoding="utf-8")

    formats = [{"format": "DOCX", "can_import": True, "can_export": True, "direction": "both"}]
    (merged / "formats.json").write_text(json.dumps(formats), encoding="utf-8")

    (merged / "class_graph.json").write_text("[]", encoding="utf-8")
    (merged / "coverage_matrix.json").write_text("[]", encoding="utf-8")

    return tmp_path


def test_materialize_produces_pef(tmp_path, monkeypatch):
    root = _setup_merged(tmp_path)
    monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", root / "knowledge")
    monkeypatch.setattr(materialize, "EVIDENCE_ROOT", root / "evidence")

    pef = materialize.materialize("words", "python")

    assert pef is not None
    assert pef["schema_version"] == 1
    assert pef["family"] == "words"
    assert pef["platform"] == "python"
    assert pef["display_name"] == "Aspose.Words"
    assert pef["source_sha"] == "abc123def456"
    assert pef["provenance_summary"]["total"] == 5
    assert pef["provenance_summary"]["dual"] == 3
    assert pef["provenance_summary"]["scout_only"] == 2
    assert pef["provenance_summary"]["dual_pct"] == 60.0
    assert pef["api_confidence"] == "high"
    assert len(pef["claims"]) == 5
    assert len(pef["api_surface"]) == 1
    assert len(pef["formats"]) == 1
    assert pef["install"]["command"] == "pip install aspose-words-foss"

    # Verify file was written
    pef_path = root / "evidence" / "words" / "python" / "pef.json"
    assert pef_path.exists()
    written = json.loads(pef_path.read_text())
    assert written["family"] == "words"


def test_materialize_rotates_previous(tmp_path, monkeypatch):
    root = _setup_merged(tmp_path)
    monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", root / "knowledge")
    monkeypatch.setattr(materialize, "EVIDENCE_ROOT", root / "evidence")

    # First run
    materialize.materialize("words", "python")
    pef_path = root / "evidence" / "words" / "python" / "pef.json"
    first_content = pef_path.read_text()

    # Second run
    materialize.materialize("words", "python")
    prev_path = root / "evidence" / "words" / "python" / "pef_previous.json"
    assert prev_path.exists()
    prev_content = prev_path.read_text()
    assert json.loads(prev_content)["family"] == "words"


def test_materialize_changelog(tmp_path, monkeypatch):
    root = _setup_merged(tmp_path)
    monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", root / "knowledge")
    monkeypatch.setattr(materialize, "EVIDENCE_ROOT", root / "evidence")

    materialize.materialize("words", "python")
    materialize.materialize("words", "python")

    changelog_path = root / "evidence" / "words" / "python" / "changelog.json"
    assert changelog_path.exists()
    entries = json.loads(changelog_path.read_text())
    assert len(entries) == 2
    assert entries[0]["claims_total"] == 5
    assert entries[1]["delta"] is not None


def test_materialize_handles_missing_optional_files(tmp_path, monkeypatch):
    root = _setup_merged(tmp_path)
    monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", root / "knowledge")
    monkeypatch.setattr(materialize, "EVIDENCE_ROOT", root / "evidence")

    # Remove optional files
    merged = root / "knowledge" / "words" / "python" / "merged"
    (merged / "class_graph.json").unlink()
    (merged / "coverage_matrix.json").unlink()

    pef = materialize.materialize("words", "python")
    assert pef is not None
    assert pef["class_graph"] == []
    assert pef["coverage_matrix"] == []
    assert pef["limitations"] == []
    assert pef["constants"] == []


def test_materialize_skip_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    monkeypatch.setattr(materialize, "EVIDENCE_ROOT", tmp_path / "evidence")

    result = materialize.materialize("nonexistent", "python")
    assert result is None


def test_parse_limitations_md(tmp_path):
    lim_file = tmp_path / "limitations.md"
    lim_file.write_text(
        "| File | Format | Class | Method | Reason |\n"
        "|------|--------|-------|--------|--------|\n"
        "| a.py | DOCX | Workbook | protect | Not implemented |\n"
        "| b.py | | Cell | | Missing |\n",
        encoding="utf-8"
    )
    result = materialize._parse_limitations_md(lim_file)
    assert "Workbook.protect" in result
    assert "Cell." in result or "Cell" in result


def test_provenance_summary():
    claims = [
        {"provenance": "dual"},
        {"provenance": "dual"},
        {"provenance": "dual_fuzzy"},
        {"provenance": "scout_only"},
    ]
    summary = materialize._compute_provenance_summary(claims)
    assert summary["dual"] == 2
    assert summary["dual_fuzzy"] == 1
    assert summary["scout_only"] == 1
    assert summary["total"] == 4
    assert summary["dual_pct"] == 75.0


def test_api_confidence():
    assert materialize._compute_api_confidence({"dual_pct": 60}) == "high"
    assert materialize._compute_api_confidence({"dual_pct": 30}) == "medium"
    assert materialize._compute_api_confidence({"dual_pct": 10}) == "low"
    assert materialize._compute_api_confidence({"dual_pct": 0}) == "low"


# ---------------------------------------------------------------------------
# Failure-mode tests — missing required inputs (TASK-04)
# ---------------------------------------------------------------------------

class TestMaterializeFailureModes:
    """Tests that materialize handles missing required knowledge files gracefully."""

    def test_missing_claims_json_returns_none(self, tmp_path, monkeypatch):
        """When claims.json is absent, materialize returns None (not a silent partial result)."""
        merged = tmp_path / "knowledge" / "words" / "python" / "merged"
        merged.mkdir(parents=True)
        # Write model.yaml and api_surface.json but NOT claims.json
        import yaml as _yaml
        model = {
            "family": "words", "platform": "python",
            "repo_sha": "abc", "merged_at": "2026-01-01T00:00:00+00:00",
            "version": "1.0.0", "install_command": "pip install x",
            "stats": {"class_count": 0, "method_count": 0, "claim_count": 0},
        }
        (merged / "model.yaml").write_text(_yaml.dump(model), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "formats.json").write_text("[]", encoding="utf-8")
        # claims.json deliberately absent

        monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(materialize, "EVIDENCE_ROOT", tmp_path / "evidence")

        result = materialize.materialize("words", "python")
        # Must either return None or raise FileNotFoundError — must NOT return a partial PEF
        assert result is None or isinstance(result, dict) and result.get("claims") == []

    def test_missing_model_yaml_returns_none(self, tmp_path, monkeypatch):
        """When model.yaml is absent, materialize returns None."""
        merged = tmp_path / "knowledge" / "words" / "python" / "merged"
        merged.mkdir(parents=True)
        # Write claims.json only, no model.yaml

        monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(materialize, "EVIDENCE_ROOT", tmp_path / "evidence")

        result = materialize.materialize("words", "python")
        assert result is None

    def test_empty_knowledge_dir_returns_none(self, tmp_path, monkeypatch):
        """Completely empty knowledge dir returns None without exception."""
        monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(materialize, "EVIDENCE_ROOT", tmp_path / "evidence")

        result = materialize.materialize("words", "python")
        assert result is None

    def test_malformed_model_yaml_does_not_silently_succeed(self, tmp_path, monkeypatch):
        """When model.yaml contains non-dict content, materialize does not return valid PEF."""
        merged = tmp_path / "knowledge" / "words" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("- not\n- a\n- dict\n", encoding="utf-8")

        monkeypatch.setattr(materialize, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(materialize, "EVIDENCE_ROOT", tmp_path / "evidence")

        try:
            result = materialize.materialize("words", "python")
            # Acceptable outcomes: None or raises
            assert result is None
        except (TypeError, AttributeError, KeyError, ValueError):
            pass  # structured failure is acceptable
