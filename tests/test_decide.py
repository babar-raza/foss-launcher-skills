"""Tests for scripts/decide.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import decide


def _make_mental_model(page_coverage=None, tiers=None):
    if page_coverage is None:
        page_coverage = {"docs": {}, "blog": {}, "kb": {}, "reference": {}}
    if tiers is None:
        tiers = {
            "tier_1_core": [{"class": "Document", "method_count": 5, "claim_count": 3, "dual_confirmed_pct": 50}],
            "tier_2_supporting": [],
            "tier_3_utility": [],
        }
    return {
        "schema_version": 1,
        "family": "words", "platform": "python",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_pef_hash": "abc123",
        "capability_tiers": tiers,
        "format_matrix": {"import": [], "export": []},
        "page_coverage": page_coverage,
        "gap_analysis": {"uncovered_tier1_classes": [], "missing_page_types": [], "forbidden_claim_count": 0},
        "readiness": {"overall": "needs_work", "blockers": [], "warnings": [], "dual_confirmed_pct": 50, "api_confidence": "medium"},
    }


def _setup_evidence(tmp_path, model, verifications=None, diff=None):
    evidence_dir = tmp_path / "evidence" / "words" / "python"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "mental_model.json").write_text(json.dumps(model), encoding="utf-8")

    if verifications:
        verify_dir = evidence_dir / "verification"
        verify_dir.mkdir()
        for slug, report in verifications.items():
            (verify_dir / f"{slug}-20260101T000000.json").write_text(json.dumps(report), encoding="utf-8")

    if diff:
        diffs_dir = evidence_dir / "diffs"
        diffs_dir.mkdir()
        (diffs_dir / "20260101T000000.json").write_text(json.dumps(diff), encoding="utf-8")

    return evidence_dir


def test_decide_create_for_missing_core_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model()
    _setup_evidence(tmp_path, model)

    result = decide.decide("words", "python")
    assert result is not None

    creates = [p for p in result["pages"] if p["action"] == "create"]
    assert len(creates) > 0
    slugs = {p["slug"] for p in creates}
    assert "installation" in slugs
    assert "quick-start" in slugs
    assert "intro" in slugs
    assert "faq" in slugs


def test_decide_create_for_tier1_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model()
    _setup_evidence(tmp_path, model)

    result = decide.decide("words", "python")
    ref_creates = [p for p in result["pages"] if p["action"] == "create" and p["site_type"] == "reference"]
    assert len(ref_creates) >= 1
    assert any(p["slug"] == "document" for p in ref_creates)


def test_decide_update_on_verification_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model(page_coverage={
        "docs": {"installation": {"status": "exists", "path": "docs/installation.md"}},
        "blog": {}, "kb": {}, "reference": {},
    })
    verifications = {
        "installation": {
            "result": "FAIL",
            "verified_at": "2026-01-01T00:00:00+00:00",
            "issues": [{"type": "forbidden_violation", "severity": "FAIL", "detail": "test"}],
        }
    }
    _setup_evidence(tmp_path, model, verifications=verifications)

    result = decide.decide("words", "python")
    install_decision = next(p for p in result["pages"] if p["slug"] == "installation")
    assert install_decision["action"] == "update"
    assert install_decision["priority"] == 1


def test_decide_no_change_when_pass_and_no_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model(page_coverage={
        "docs": {"installation": {"status": "exists", "path": "docs/installation.md"}},
        "blog": {}, "kb": {}, "reference": {},
    })
    verifications = {
        "installation": {
            "result": "PASS",
            "verified_at": "2026-01-01T00:00:00+00:00",
            "issues": [],
        }
    }
    _setup_evidence(tmp_path, model, verifications=verifications)

    result = decide.decide("words", "python")
    install_decision = next(p for p in result["pages"] if p["slug"] == "installation")
    assert install_decision["action"] == "no_change"
    assert install_decision["priority"] == 5


def test_decide_verify_only_on_pass_with_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model(page_coverage={
        "docs": {"installation": {"status": "exists", "path": "docs/installation.md"}},
        "blog": {}, "kb": {}, "reference": {},
    })
    verifications = {
        "installation": {"result": "PASS", "verified_at": "2026-01-01T00:00:00+00:00", "issues": []}
    }
    diff = {
        "schema_version": 1,
        "claims": {"added": [{"claim_id": "c99"}], "removed": [], "modified": []},
        "api_surface": {"classes_added": [], "classes_removed": [], "methods_added": [], "methods_removed": []},
        "formats": {"added": [], "removed": []},
        "impact_summary": {"severity": "LOW", "affected_page_types": ["docs"], "recommendation": "test"},
    }
    _setup_evidence(tmp_path, model, verifications=verifications, diff=diff)

    result = decide.decide("words", "python")
    install_decision = next(p for p in result["pages"] if p["slug"] == "installation")
    assert install_decision["action"] == "verify_only"


def test_priority_ordering(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model()
    _setup_evidence(tmp_path, model)

    result = decide.decide("words", "python")
    priorities = [p["priority"] for p in result["pages"]]
    assert priorities == sorted(priorities)


def test_summary_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    model = _make_mental_model()
    _setup_evidence(tmp_path, model)

    result = decide.decide("words", "python")
    summary = result["summary"]
    total = summary["create"] + summary["update"] + summary["enhance"] + summary["verify_only"] + summary["no_change"]
    assert total == summary["total"]
    assert total == len(result["pages"])


def test_skip_missing_model(tmp_path, monkeypatch):
    monkeypatch.setattr(decide, "EVIDENCE_ROOT", tmp_path / "evidence")
    result = decide.decide("nonexistent", "python")
    assert result is None
