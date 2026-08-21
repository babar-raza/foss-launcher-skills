"""
Tests for scripts/pipeline/commands/knowledge/changelog_grounding.py.

MT036-2026-08-21 (PDF/Java Maven publish hardening, gap G5). Covers: category mapping
from semantic_diff.py's typed change objects, the grounding validator's rejection of
uncited/fabricated symbols and marketing language, INTERNAL_ONLY filtering, and the
CLI's file-not-found guidance when semantic_changes.json hasn't been produced yet.
"""

import json
from pathlib import Path

import pytest

import commands.knowledge.changelog_grounding as sut


@pytest.fixture(autouse=True)
def reset_config():
    yield
    sut.configure(reports_root="reports/refresh_review")


def _change(
    change_type,
    symbol,
    symbol_kind="class",
    public_impact="USER_VISIBLE",
    evidence_paths=None,
    change_id="CHG-pdf-java-0001",
):
    return {
        "change_id": change_id,
        "family": "pdf",
        "platform": "java",
        "base_sha": "aaa",
        "current_sha": "bbb",
        "evidence_paths": evidence_paths if evidence_paths is not None else ["knowledge/pdf/java/merged/knowledge_delta.json"],
        "change_type": change_type,
        "symbol": symbol,
        "symbol_kind": symbol_kind,
        "public_impact": public_impact,
        "content_impact": "BODY_UPDATE",
        "confidence": 0.95,
    }


def _draft(changes, **overrides):
    kwargs = dict(
        family="pdf", platform="java",
        previous_version="26.6.0", new_version="26.8.0",
        group_id="org.aspose", artifact_id="aspose-pdf-foss",
        released_at="2026-08-21",
    )
    kwargs.update(overrides)
    return sut.build_changelog_draft(changes, **kwargs)


# ── build_changelog_draft: category mapping ─────────────────────────────────


def test_api_added_maps_to_added_category():
    changes = [_change("API_ADDED", "PdfDigitalSignatureBuilder")]
    draft = _draft(changes)
    assert len(draft["categories"]["Added"]) == 1
    assert draft["categories"]["Added"][0]["symbol"] == "PdfDigitalSignatureBuilder"


def test_api_resurrected_maps_to_added_category():
    changes = [_change("API_RESURRECTED", "PdfAValidator")]
    draft = _draft(changes)
    assert len(draft["categories"]["Added"]) == 1


def test_api_modified_maps_to_changed_category():
    changes = [_change("API_MODIFIED", "Document")]
    draft = _draft(changes)
    assert len(draft["categories"]["Changed"]) == 1


def test_behavior_changed_maps_to_changed_category():
    changes = [_change("BEHAVIOR_CHANGED", "CLM-pdf-abc123", symbol_kind="claim")]
    draft = _draft(changes)
    assert len(draft["categories"]["Changed"]) == 1


def test_api_removed_maps_to_removed_category_and_breaking():
    changes = [_change("API_REMOVED", "LegacyPdfWriter")]
    draft = _draft(changes)
    assert len(draft["categories"]["Removed"]) == 1
    assert len(draft["breaking_changes"]) == 1
    assert draft["migration_guidance"]  # non-empty for a breaking change


def test_internal_only_changes_are_excluded_from_every_category():
    """A real, valid semantic_diff.py finding (internal helper class changed) must
    never leak into the public-facing changelog -- confirmed noise for a Maven
    Central consumer, not a defect in semantic_diff.py's own classification."""
    changes = [_change("API_MODIFIED", "InternalPdfEngineHelper", public_impact="INTERNAL_ONLY")]
    draft = _draft(changes)
    total = sum(len(v) for v in draft["categories"].values())
    assert total == 0
    assert draft["breaking_changes"] == []


def test_no_deprecated_entries_are_ever_fabricated():
    """semantic_diff.py has no DEPRECATED change type -- the category must stay
    empty, never synthesized from something else."""
    changes = [_change("API_MODIFIED", "Document"), _change("API_ADDED", "NewClass")]
    draft = _draft(changes)
    assert draft["categories"]["Deprecated"] == []


# ── validate_changelog_draft ─────────────────────────────────────────────────


def test_valid_draft_produces_no_violations():
    changes = [_change("API_ADDED", "PdfDigitalSignatureBuilder")]
    draft = _draft(changes)
    assert sut.validate_changelog_draft(draft, changes) == []


def test_fabricated_symbol_not_in_source_data_is_rejected():
    """The core grounding guarantee: a symbol appearing in the draft that has no
    matching entry in the real semantic_changes.json data must be caught, even if
    it was inserted by hand-editing the draft after the fact."""
    changes = [_change("API_ADDED", "RealClass")]
    draft = _draft(changes)
    draft["categories"]["Added"].append({
        "symbol": "FabricatedClassNeverInSourceData", "symbol_kind": "class",
        "change_id": "CHG-fake-0001", "evidence_paths": ["made/up/path.json"],
    })
    violations = sut.validate_changelog_draft(draft, changes)
    assert any("FabricatedClassNeverInSourceData" in v for v in violations)


def test_entry_with_no_evidence_paths_is_rejected():
    changes = [_change("API_ADDED", "RealClass", evidence_paths=[])]
    draft = _draft(changes)
    violations = sut.validate_changelog_draft(draft, changes)
    assert any("no evidence_paths" in v for v in violations)


@pytest.mark.parametrize("phrase", ["blazing fast", "seamless", "industry-leading", "cutting-edge"])
def test_marketing_language_is_rejected(phrase):
    changes = [_change("API_ADDED", "RealClass")]
    draft = _draft(changes)
    draft["migration_guidance"] = [f"This release is {phrase} and better than ever."]
    violations = sut.validate_changelog_draft(draft, changes)
    assert any("marketing language" in v.lower() for v in violations)


def test_missing_maven_coordinates_is_rejected():
    changes = [_change("API_ADDED", "RealClass")]
    draft = _draft(changes)
    draft["maven"] = {}
    violations = sut.validate_changelog_draft(draft, changes)
    assert any("Maven coordinates" in v for v in violations)


def test_empty_draft_on_a_republish_is_rejected():
    """A genuinely empty changelog on a version bump (previous_version set) is
    treated as a suspicious signal, not silently accepted -- likely means
    semantic_changes.json wasn't regenerated for the real new version."""
    draft = _draft([])
    violations = sut.validate_changelog_draft(draft, [])
    assert any("empty for a republish" in v for v in violations)


# ── format_markdown ───────────────────────────────────────────────────────────


def test_format_markdown_includes_version_header_and_maven_block():
    changes = [_change("API_ADDED", "PdfDigitalSignatureBuilder")]
    draft = _draft(changes)
    body = sut.format_markdown(draft)
    assert "## 26.8.0" in body
    assert "### Added" in body
    assert "PdfDigitalSignatureBuilder" in body
    assert "org.aspose" in body and "aspose-pdf-foss" in body


def test_format_markdown_omits_empty_categories():
    changes = [_change("API_ADDED", "OnlyThisOne")]
    draft = _draft(changes)
    body = sut.format_markdown(draft)
    assert "### Removed" not in body
    assert "### Fixed" not in body


# ── load_semantic_changes / CLI plumbing ─────────────────────────────────────


def test_load_semantic_changes_reads_real_file(tmp_path):
    reports = tmp_path / "reports" / "refresh_review"
    (reports / "pdf" / "java").mkdir(parents=True)
    payload = [dict(_change("API_ADDED", "X"))]
    (reports / "pdf" / "java" / "semantic_changes.json").write_text(json.dumps(payload), encoding="utf-8")
    sut.configure(reports_root=str(reports))
    loaded = sut.load_semantic_changes("pdf", "java")
    assert loaded == payload


def test_load_semantic_changes_missing_file_gives_actionable_error(tmp_path):
    sut.configure(reports_root=str(tmp_path / "nonexistent"))
    with pytest.raises(FileNotFoundError, match="knowledge-diff"):
        sut.load_semantic_changes("pdf", "java")


def test_cli_exits_nonzero_on_validation_failure(tmp_path, capsys):
    reports = tmp_path / "reports" / "refresh_review"
    (reports / "pdf" / "java").mkdir(parents=True)
    (reports / "pdf" / "java" / "semantic_changes.json").write_text("[]", encoding="utf-8")
    sut.configure(reports_root=str(reports))
    try:
        exit_code = sut.main([
            "pdf", "java", "--previous-version", "26.6.0", "--new-version", "26.8.0",
            "--artifact-id", "aspose-pdf-foss",
        ])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATION FAILED" in captured.err
    finally:
        sut.configure(reports_root="reports/refresh_review")


def test_cli_succeeds_and_prints_markdown_on_valid_data(tmp_path, capsys):
    reports = tmp_path / "reports" / "refresh_review"
    (reports / "pdf" / "java").mkdir(parents=True)
    payload = [dict(_change("API_ADDED", "PdfDigitalSignatureBuilder"))]
    (reports / "pdf" / "java" / "semantic_changes.json").write_text(json.dumps(payload), encoding="utf-8")
    sut.configure(reports_root=str(reports))
    try:
        exit_code = sut.main([
            "pdf", "java", "--previous-version", "26.6.0", "--new-version", "26.8.0",
            "--artifact-id", "aspose-pdf-foss",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PdfDigitalSignatureBuilder" in captured.out
    finally:
        sut.configure(reports_root="reports/refresh_review")
