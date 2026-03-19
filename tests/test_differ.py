"""Tests for scripts/differ.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import differ


def _make_pef(claims=None, api=None, formats=None, sha="abc123"):
    if claims is None:
        claims = [
            {"claim_id": "c1", "kind": "api_class", "text": "Document class", "confidence": 0.9, "provenance": "dual"},
            {"claim_id": "c2", "kind": "api_method", "text": "Document.load", "confidence": 0.95, "provenance": "dual"},
        ]
    if api is None:
        api = [{"name": "Document", "kind": "class", "methods": [{"name": "load"}, {"name": "save"}]}]
    if formats is None:
        formats = [{"format": "DOCX", "can_import": True, "can_export": True, "direction": "both"}]

    return {
        "schema_version": 1,
        "family": "words", "platform": "python",
        "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": sha,
        "claims": claims, "api_surface": api, "formats": formats,
    }


def test_diff_detects_added_claims():
    old = _make_pef()
    new_claims = old["claims"] + [
        {"claim_id": "c3", "kind": "api_method", "text": "Document.convert", "confidence": 0.8, "provenance": "scout_only"}
    ]
    new = _make_pef(claims=new_claims, sha="def456")

    report = differ.diff_pefs(old, new)
    assert len(report["claims"]["added"]) == 1
    assert report["claims"]["added"][0]["claim_id"] == "c3"
    assert len(report["claims"]["removed"]) == 0


def test_diff_detects_removed_claims():
    old = _make_pef()
    new = _make_pef(claims=[old["claims"][0]], sha="def456")  # Remove c2

    report = differ.diff_pefs(old, new)
    assert len(report["claims"]["removed"]) == 1
    assert report["claims"]["removed"][0]["claim_id"] == "c2"


def test_diff_detects_modified_claims():
    old = _make_pef()
    new_claims = [
        {"claim_id": "c1", "kind": "api_class", "text": "Document class handles Word docs", "confidence": 0.95, "provenance": "dual"},
        old["claims"][1],
    ]
    new = _make_pef(claims=new_claims, sha="def456")

    report = differ.diff_pefs(old, new)
    assert len(report["claims"]["modified"]) == 1
    assert report["claims"]["modified"][0]["claim_id"] == "c1"
    assert report["claims"]["modified"][0]["confidence_delta"] == 0.05


def test_diff_detects_added_classes():
    old = _make_pef()
    new_api = old["api_surface"] + [{"name": "Paragraph", "kind": "class", "methods": []}]
    new = _make_pef(api=new_api, sha="def456")

    report = differ.diff_pefs(old, new)
    assert "Paragraph" in report["api_surface"]["classes_added"]


def test_diff_detects_removed_classes():
    old = _make_pef()
    new = _make_pef(api=[], sha="def456")

    report = differ.diff_pefs(old, new)
    assert "Document" in report["api_surface"]["classes_removed"]


def test_diff_severity_high_on_api_removal():
    old = _make_pef()
    new = _make_pef(api=[], sha="def456")

    report = differ.diff_pefs(old, new)
    assert report["impact_summary"]["severity"] == "HIGH"


def test_diff_severity_none_when_identical():
    pef = _make_pef()
    report = differ.diff_pefs(pef, pef)
    assert report["impact_summary"]["severity"] == "NONE"
    assert len(report["claims"]["added"]) == 0
    assert len(report["claims"]["removed"]) == 0


def test_diff_severity_low_on_additions_only():
    old = _make_pef()
    new_claims = old["claims"] + [
        {"claim_id": "c3", "kind": "api_method", "text": "New method", "confidence": 0.8, "provenance": "scout_only"}
    ]
    new = _make_pef(claims=new_claims, sha="def456")

    report = differ.diff_pefs(old, new)
    assert report["impact_summary"]["severity"] == "LOW"


def test_diff_format_changes():
    old = _make_pef()
    new_formats = [
        {"format": "DOCX", "can_import": True, "can_export": True, "direction": "both"},
        {"format": "PDF", "can_import": False, "can_export": True, "direction": "export"},
    ]
    new = _make_pef(formats=new_formats, sha="def456")

    report = differ.diff_pefs(old, new)
    assert len(report["formats"]["added"]) == 1
    assert report["formats"]["added"][0]["format"] == "PDF"


def test_diff_product_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(differ, "EVIDENCE_ROOT", tmp_path / "evidence")

    evidence_dir = tmp_path / "evidence" / "words" / "python"
    evidence_dir.mkdir(parents=True)

    old = _make_pef(sha="old123")
    new = _make_pef(sha="new456")
    new["claims"].append({"claim_id": "c3", "kind": "api_method", "text": "Extra", "provenance": "scout_only"})

    (evidence_dir / "pef_previous.json").write_text(json.dumps(old), encoding="utf-8")
    (evidence_dir / "pef.json").write_text(json.dumps(new), encoding="utf-8")

    report = differ.diff_product("words", "python")
    assert report is not None
    assert report["impact_summary"]["severity"] == "LOW"

    diffs_dir = evidence_dir / "diffs"
    assert diffs_dir.exists()
    diff_files = list(diffs_dir.glob("*.json"))
    assert len(diff_files) == 1
