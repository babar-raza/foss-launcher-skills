"""Tests for lib/product_state.py — transitions, stop reasons, phase inference."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import sys
_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.product_state import (
    ALLOWED_TRANSITIONS,
    MAX_RETRIES,
    PRODUCT_STATE_SCHEMA_VERSION,
    IllegalTransitionError,
    Phase,
    ProductState,
    StopReason,
    infer_phase,
)


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

class TestValidTransitions:
    def test_discovered_to_snapshot(self):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SNAPSHOT_CAPTURED, reason="initial scout")
        assert state.phase == Phase.SNAPSHOT_CAPTURED.value
        assert state.stop_reason == StopReason.CONTINUE.value
        assert len(state.transition_history) == 1

    def test_full_happy_path(self):
        """Walk the entire happy path from DISCOVERED to READY_FOR_REVIEW."""
        state = ProductState(family="pdf", platform="go")
        happy_path = [
            Phase.SNAPSHOT_CAPTURED,
            Phase.FACTS_EXTRACTED,
            Phase.FACTS_VERIFIED,
            Phase.PLAN_COMPILED,
            Phase.CONTENT_GENERATED,
            Phase.CLAIMS_VERIFIED,
            Phase.QUALITY_EVALUATED,
            Phase.REGRESSION_PASSED,
            Phase.READY_FOR_REVIEW,
        ]
        for phase in happy_path:
            state.transition(phase)
        assert state.phase == Phase.READY_FOR_REVIEW.value
        assert state.stop_reason == StopReason.READY_FOR_HUMAN_REVIEW.value
        assert len(state.transition_history) == len(happy_path)

    def test_discovered_to_source_changed(self):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SOURCE_CHANGED)
        assert state.phase == Phase.SOURCE_CHANGED.value

    def test_blocked_external_and_back(self):
        state = ProductState(family="pdf", platform="go")
        # Get to READY_FOR_REVIEW
        for p in [Phase.SNAPSHOT_CAPTURED, Phase.FACTS_EXTRACTED, Phase.FACTS_VERIFIED,
                   Phase.PLAN_COMPILED, Phase.CONTENT_GENERATED, Phase.CLAIMS_VERIFIED,
                   Phase.QUALITY_EVALUATED, Phase.REGRESSION_PASSED, Phase.READY_FOR_REVIEW]:
            state.transition(p)
        state.transition(Phase.BLOCKED_EXTERNAL)
        assert state.stop_reason == StopReason.BLOCKED_EXTERNAL_APPROVAL.value
        state.transition(Phase.READY_FOR_REVIEW)
        assert state.stop_reason == StopReason.READY_FOR_HUMAN_REVIEW.value


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    def test_discovered_to_facts_extracted(self):
        state = ProductState(family="pdf", platform="go")
        with pytest.raises(IllegalTransitionError):
            state.transition(Phase.FACTS_EXTRACTED)

    def test_ready_for_review_to_content_generated(self):
        state = ProductState(family="pdf", platform="go")
        for p in [Phase.SNAPSHOT_CAPTURED, Phase.FACTS_EXTRACTED, Phase.FACTS_VERIFIED,
                   Phase.PLAN_COMPILED, Phase.CONTENT_GENERATED, Phase.CLAIMS_VERIFIED,
                   Phase.QUALITY_EVALUATED, Phase.REGRESSION_PASSED, Phase.READY_FOR_REVIEW]:
            state.transition(p)
        with pytest.raises(IllegalTransitionError):
            state.transition(Phase.CONTENT_GENERATED)

    def test_quarantined_only_allows_discovered(self):
        state = ProductState(phase=Phase.QUARANTINED.value)
        with pytest.raises(IllegalTransitionError):
            state.transition(Phase.SNAPSHOT_CAPTURED)
        # But DISCOVERED should work
        state.transition(Phase.DISCOVERED)
        assert state.phase == Phase.DISCOVERED.value


# ---------------------------------------------------------------------------
# Retry and auto-quarantine
# ---------------------------------------------------------------------------

class TestRetryMechanics:
    def test_retry_increments_count(self):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SNAPSHOT_CAPTURED)
        state.transition(Phase.RETRYABLE_FAILURE)
        assert state.retry_count == 1
        assert state.stop_reason == StopReason.RETRYABLE_FAILURE.value

    def test_auto_quarantine_after_max_retries(self):
        """After MAX_RETRIES consecutive failures (no recovery), auto-quarantine."""
        state = ProductState(family="pdf", platform="go")
        # Manually set retry_count to MAX_RETRIES - 1 and phase to a retryable state
        state.phase = Phase.SOURCE_CHANGED.value
        state.retry_count = MAX_RETRIES - 1
        # This final retry should trigger auto-quarantine
        state.transition(Phase.RETRYABLE_FAILURE)
        assert state.phase == Phase.QUARANTINED.value
        assert state.stop_reason == StopReason.QUARANTINED_REPEATED_FAILURE.value

    def test_successful_recovery_resets_count(self):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SNAPSHOT_CAPTURED)
        state.transition(Phase.RETRYABLE_FAILURE)
        assert state.retry_count == 1
        # Recover
        state.transition(Phase.SNAPSHOT_CAPTURED)
        assert state.retry_count == 0


# ---------------------------------------------------------------------------
# Stop reason classification
# ---------------------------------------------------------------------------

class TestStopReasons:
    def test_continue_on_normal_transition(self):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SNAPSHOT_CAPTURED)
        assert state.stop_reason == StopReason.CONTINUE.value

    def test_blocked_external(self):
        state = ProductState(phase=Phase.READY_FOR_REVIEW.value)
        state.transition(Phase.BLOCKED_EXTERNAL)
        assert state.stop_reason == StopReason.BLOCKED_EXTERNAL_APPROVAL.value

    def test_ready_for_review(self):
        state = ProductState(phase=Phase.REGRESSION_PASSED.value)
        state.transition(Phase.READY_FOR_REVIEW)
        assert state.stop_reason == StopReason.READY_FOR_HUMAN_REVIEW.value


# ---------------------------------------------------------------------------
# Terminal / actionable checks
# ---------------------------------------------------------------------------

class TestStateQueries:
    def test_terminal_states(self):
        for phase in [Phase.READY_FOR_REVIEW, Phase.BLOCKED_EXTERNAL, Phase.QUARANTINED]:
            state = ProductState(phase=phase.value)
            assert state.is_terminal(), f"{phase} should be terminal"

    def test_non_terminal_states(self):
        for phase in [Phase.DISCOVERED, Phase.SNAPSHOT_CAPTURED, Phase.FACTS_EXTRACTED]:
            state = ProductState(phase=phase.value)
            assert not state.is_terminal(), f"{phase} should not be terminal"

    def test_actionable_when_continue(self):
        state = ProductState(phase=Phase.SNAPSHOT_CAPTURED.value, stop_reason=StopReason.CONTINUE.value)
        assert state.is_actionable()

    def test_not_actionable_when_terminal(self):
        state = ProductState(phase=Phase.QUARANTINED.value, stop_reason=StopReason.QUARANTINED_REPEATED_FAILURE.value)
        assert not state.is_actionable()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict(self):
        state = ProductState(family="pdf", platform="go")
        d = state.to_dict()
        assert d["family"] == "pdf"
        assert d["schema_version"] == PRODUCT_STATE_SCHEMA_VERSION

    def test_roundtrip_json(self):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SNAPSHOT_CAPTURED)
        json_str = state.to_json()
        restored = ProductState.from_dict(json.loads(json_str))
        assert restored.phase == state.phase
        assert restored.family == "pdf"
        assert len(restored.transition_history) == 1

    def test_write_and_read(self, tmp_path):
        state = ProductState(family="pdf", platform="go")
        state.transition(Phase.SNAPSHOT_CAPTURED)
        path = tmp_path / "state.json"
        state.write(path)
        restored = ProductState.read(path)
        assert restored.phase == state.phase
        assert restored.family == state.family


# ---------------------------------------------------------------------------
# Phase inference
# ---------------------------------------------------------------------------

class TestInferPhase:
    def test_no_artifacts_discovered(self, tmp_path):
        assert infer_phase("pdf", "go", tmp_path) == Phase.DISCOVERED

    def test_scout_only_snapshot_captured(self, tmp_path):
        scout = tmp_path / "pdf" / "go" / "scout"
        scout.mkdir(parents=True)
        (scout / "raw.json").write_text("{}", encoding="utf-8")
        assert infer_phase("pdf", "go", tmp_path) == Phase.SNAPSHOT_CAPTURED

    def test_scout_api_surface_facts_extracted(self, tmp_path):
        scout = tmp_path / "pdf" / "go" / "scout"
        scout.mkdir(parents=True)
        (scout / "api_surface.json").write_text("{}", encoding="utf-8")
        assert infer_phase("pdf", "go", tmp_path) == Phase.FACTS_EXTRACTED

    def test_merged_api_surface_facts_extracted(self, tmp_path):
        merged = tmp_path / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("{}", encoding="utf-8")
        assert infer_phase("pdf", "go", tmp_path) == Phase.FACTS_EXTRACTED

    def test_merged_with_claims_facts_verified(self, tmp_path):
        merged = tmp_path / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("{}", encoding="utf-8")
        (merged / "claims.json").write_text("{}", encoding="utf-8")
        assert infer_phase("pdf", "go", tmp_path) == Phase.FACTS_VERIFIED


# ---------------------------------------------------------------------------
# Transition graph coverage
# ---------------------------------------------------------------------------

class TestTransitionCoverage:
    def test_all_phases_have_transitions(self):
        """Every phase should appear as a key in ALLOWED_TRANSITIONS."""
        for phase in Phase:
            assert phase in ALLOWED_TRANSITIONS, f"{phase} missing from ALLOWED_TRANSITIONS"

    def test_no_self_transitions(self):
        """No phase should transition to itself."""
        for phase, targets in ALLOWED_TRANSITIONS.items():
            assert phase not in targets, f"{phase} allows self-transition"
