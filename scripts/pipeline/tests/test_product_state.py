"""
Tests for scripts/pipeline/lib/product_state.py.

Covers infer_phase() artifact-presence inference (including the
enrichment_status gate) and ProductState transition validation.
"""

import json
from pathlib import Path

import pytest
import yaml

from lib.product_state import (
    ALLOWED_TRANSITIONS,
    MAX_RETRIES,
    IllegalTransitionError,
    Phase,
    ProductState,
    StopReason,
    infer_phase,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _write_model_yaml(merged: Path, **fields) -> None:
    merged.mkdir(parents=True, exist_ok=True)
    data = {"repo_sha": "abc123"}
    data.update(fields)
    (merged / "model.yaml").write_text(yaml.dump(data), encoding="utf-8")


# ── infer_phase() ────────────────────────────────────────────────────────


def test_infer_phase_no_artifacts_returns_discovered(tmp_path):
    kr = tmp_path / "knowledge"
    assert infer_phase("pdf", "net", kr) == Phase.DISCOVERED


def test_infer_phase_scout_only_dir_returns_facts_extracted(tmp_path):
    kr = tmp_path / "knowledge"
    scout = kr / "pdf" / "net" / "scout"
    scout.mkdir(parents=True)
    (scout / "api_surface.json").write_text("{}", encoding="utf-8")
    assert infer_phase("pdf", "net", kr) == Phase.FACTS_EXTRACTED


def test_infer_phase_merged_no_api_surface_returns_snapshot_captured(tmp_path):
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "net" / "merged"
    merged.mkdir(parents=True)
    assert infer_phase("pdf", "net", kr) == Phase.SNAPSHOT_CAPTURED


def test_infer_phase_stale_since_returns_source_changed(tmp_path):
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "net" / "merged"
    _write_model_yaml(merged, enrichment_status="full", stale_since="2026-07-01")
    (merged / "api_surface.json").write_text("{}", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    assert infer_phase("pdf", "net", kr) == Phase.SOURCE_CHANGED


def test_infer_phase_scout_only_enrichment_returns_facts_extracted(tmp_path):
    """The core regression case: claims.json exists but enrichment_status
    is scout-only — must NOT be reported as FACTS_VERIFIED."""
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "net" / "merged"
    _write_model_yaml(merged, enrichment_status="scout-only")
    (merged / "api_surface.json").write_text("{}", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    assert infer_phase("pdf", "net", kr) == Phase.FACTS_EXTRACTED


def test_infer_phase_full_enrichment_returns_facts_verified(tmp_path):
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "go" / "merged"
    _write_model_yaml(merged, enrichment_status="full")
    (merged / "api_surface.json").write_text("{}", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    assert infer_phase("pdf", "go", kr) == Phase.FACTS_VERIFIED


def test_infer_phase_missing_enrichment_status_field_defaults_verified(tmp_path):
    """Backward compatibility: model.yaml without an enrichment_status field
    (schema predates this gate) keeps the pre-existing behavior."""
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "go" / "merged"
    _write_model_yaml(merged)  # no enrichment_status key
    (merged / "api_surface.json").write_text("{}", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    assert infer_phase("pdf", "go", kr) == Phase.FACTS_VERIFIED


def test_infer_phase_merged_no_claims_returns_facts_extracted(tmp_path):
    kr = tmp_path / "knowledge"
    merged = kr / "pdf" / "go" / "merged"
    _write_model_yaml(merged, enrichment_status="full")
    (merged / "api_surface.json").write_text("{}", encoding="utf-8")
    assert infer_phase("pdf", "go", kr) == Phase.FACTS_EXTRACTED


# ── ProductState.transition() ────────────────────────────────────────────


def test_transition_valid_advances_phase():
    state = ProductState(family="pdf", platform="go", phase=Phase.DISCOVERED.value)
    state.transition(Phase.SOURCE_CHANGED, reason="S-12: SHA drift detected")
    assert state.phase == Phase.SOURCE_CHANGED.value
    assert state.stop_reason == StopReason.CONTINUE.value
    assert len(state.transition_history) == 1
    assert state.transition_history[0]["reason"] == "S-12: SHA drift detected"


def test_transition_illegal_raises():
    state = ProductState(family="pdf", platform="go", phase=Phase.DISCOVERED.value)
    with pytest.raises(IllegalTransitionError):
        state.transition(Phase.DRAFT_WRITTEN)


def test_transition_retry_count_increments():
    state = ProductState(family="pdf", platform="go", phase=Phase.FACTS_EXTRACTED.value)
    state.transition(Phase.RETRYABLE_FAILURE)
    assert state.retry_count == 1
    assert state.phase == Phase.RETRYABLE_FAILURE.value


def test_transition_auto_quarantines_after_max_retries():
    """RETRYABLE_FAILURE has no self-loop in ALLOWED_TRANSITIONS, so retry_count
    can only be driven to the MAX_RETRIES boundary directly (not through repeated
    transition() calls, which reset the counter on recovery). This exercises the
    `retry_count >= MAX_RETRIES` auto-quarantine guard in transition() itself."""
    state = ProductState(family="pdf", platform="go", phase=Phase.FACTS_EXTRACTED.value,
                          retry_count=MAX_RETRIES - 1)
    state.transition(Phase.RETRYABLE_FAILURE)
    assert state.phase == Phase.QUARANTINED.value
    assert state.stop_reason == StopReason.QUARANTINED_REPEATED_FAILURE.value


def test_write_and_read_roundtrip(tmp_path):
    state = ProductState(family="pdf", platform="go", phase=Phase.FACTS_VERIFIED.value)
    path = tmp_path / "product_states" / "pdf-go.json"
    state.write(path)
    loaded = ProductState.read(path)
    assert loaded.family == "pdf"
    assert loaded.platform == "go"
    assert loaded.phase == Phase.FACTS_VERIFIED.value


def test_is_terminal_true_for_ready_for_review():
    state = ProductState(phase=Phase.READY_FOR_REVIEW.value)
    assert state.is_terminal() is True


def test_is_actionable_false_when_blocked():
    state = ProductState(phase=Phase.BLOCKED_EXTERNAL.value, stop_reason=StopReason.BLOCKED_EXTERNAL_APPROVAL.value)
    assert state.is_actionable() is False


def test_all_phases_reachable_in_allowed_transitions():
    """Every non-terminal phase must have at least one outgoing transition."""
    terminal = {Phase.READY_FOR_REVIEW, Phase.APPROVED_FOR_DRAFT_WRITE,
                Phase.DRAFT_WRITTEN, Phase.BLOCKED_EXTERNAL, Phase.QUARANTINED}
    for phase in Phase:
        if phase in terminal:
            continue
        assert phase in ALLOWED_TRANSITIONS, f"{phase} has no outgoing transitions defined"
