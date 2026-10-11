"""Tests for schema_validators.py — schema validation + negative tests for all ACT modules."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.schema_validators import (
    ValidationError,
    validate_and_raise,
    validate_external_signals,
    validate_fact_graph,
    validate_next_action,
    validate_page_plan,
    validate_product_state,
)
from lib.fact_graph import Fact, FactGraph, FactType, compile_fact_graph
from lib.product_state import IllegalTransitionError, Phase, ProductState
from lib.external_signals import ExternalSignal, SignalBatch


# ---------------------------------------------------------------------------
# Fact graph schema validation
# ---------------------------------------------------------------------------

class TestFactGraphSchema:
    def test_valid_graph(self):
        graph = FactGraph(family="pdf", platform="go")
        graph.add_fact(Fact(
            fact_id="FG-abc", fact_type="source", category="api_class",
            family="pdf", platform="go", text="Doc",
        ))
        errors = validate_fact_graph(graph.to_dict())
        assert errors == []

    def test_missing_required_keys(self):
        errors = validate_fact_graph({"family": "pdf"})
        assert len(errors) > 0
        assert any("schema_version" in e for e in errors)

    def test_invalid_fact_type(self):
        data = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "fact_count": 1, "facts": [{
                "fact_id": "FG-x", "fact_type": "BOGUS", "category": "claim",
                "family": "pdf", "platform": "go", "text": "x",
            }],
        }
        errors = validate_fact_graph(data)
        assert any("invalid fact_type" in e for e in errors)

    def test_invalid_verification_status(self):
        data = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "fact_count": 1, "facts": [{
                "fact_id": "FG-x", "fact_type": "source", "category": "claim",
                "family": "pdf", "platform": "go", "text": "x",
                "verification_status": "WRONG",
            }],
        }
        errors = validate_fact_graph(data)
        assert any("invalid verification_status" in e for e in errors)

    def test_confidence_out_of_range(self):
        data = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "fact_count": 1, "facts": [{
                "fact_id": "FG-x", "fact_type": "source", "category": "claim",
                "family": "pdf", "platform": "go", "text": "x",
                "confidence": 1.5,
            }],
        }
        errors = validate_fact_graph(data)
        assert any("confidence" in e for e in errors)

    def test_validate_and_raise(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_and_raise({}, validate_fact_graph)
        assert len(exc_info.value.errors) > 0


# ---------------------------------------------------------------------------
# Page plan schema validation
# ---------------------------------------------------------------------------

class TestPagePlanSchema:
    def test_valid_plan(self):
        plan = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "total_page_count": 1, "subdomains": {
                "reference": {
                    "page_count": 1,
                    "pages": [{"page_type": "reference", "slug": "ref/pdf/go/doc",
                               "title": "Doc", "required_sections": ["desc"],
                               "required_facts": ["FG-x"]}],
                }
            },
        }
        errors = validate_page_plan(plan)
        assert errors == []

    def test_missing_page_fields(self):
        plan = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "total_page_count": 1, "subdomains": {
                "reference": {"page_count": 1, "pages": [{"slug": "x"}]},
            },
        }
        errors = validate_page_plan(plan)
        assert any("page_type" in e for e in errors)


# ---------------------------------------------------------------------------
# Product state schema validation
# ---------------------------------------------------------------------------

class TestProductStateSchema:
    def test_valid_state(self):
        state = ProductState(family="pdf", platform="go")
        errors = validate_product_state(state.to_dict())
        assert errors == []

    def test_invalid_phase(self):
        errors = validate_product_state({
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "phase": "INVALID_PHASE", "stop_reason": "continue_autonomously",
        })
        assert any("invalid phase" in e for e in errors)


# ---------------------------------------------------------------------------
# External signals schema validation
# ---------------------------------------------------------------------------

class TestExternalSignalsSchema:
    def test_valid_batch(self):
        batch = SignalBatch(family="pdf", platform="go", source="test")
        batch.add_signal(ExternalSignal(signal_type="test", text="t", source="test"))
        errors = validate_external_signals(batch.to_dict())
        assert errors == []

    def test_advisory_must_be_true(self):
        data = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "source": "test", "signal_count": 1, "signals": [{
                "signal_type": "test", "text": "t", "source": "test",
                "advisory": False,
            }],
        }
        errors = validate_external_signals(data)
        assert any("advisory must be True" in e for e in errors)


# ---------------------------------------------------------------------------
# Next action schema validation
# ---------------------------------------------------------------------------

class TestNextActionSchema:
    def test_valid_action(self):
        data = {
            "schema_version": "1.0.0", "action_id": "scout",
            "family": "pdf", "platform": "go", "phase": "discovered",
            "stop_reason": "continue_autonomously",
            "description": "Extract facts", "command": "repo-scout pdf go",
            "dry_run": True,
        }
        errors = validate_next_action(data)
        assert errors == []

    def test_dry_run_must_be_true(self):
        data = {
            "schema_version": "1.0.0", "action_id": "scout",
            "family": "pdf", "platform": "go", "phase": "discovered",
            "dry_run": False,
        }
        errors = validate_next_action(data)
        assert any("dry_run must be True" in e for e in errors)


# ---------------------------------------------------------------------------
# Negative tests for fact_graph module
# ---------------------------------------------------------------------------

class TestFactGraphNegative:
    def test_compile_missing_merged_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compile_fact_graph("nonexistent", "nope", tmp_path)

    def test_malformed_claims_json(self, tmp_path):
        """Malformed claims.json should not crash; should produce 0 claim facts."""
        merged = tmp_path / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("repo_sha: abc\n", encoding="utf-8")
        (merged / "claims.json").write_text("not valid json {{", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            compile_fact_graph("pdf", "go", tmp_path)

    def test_duplicate_fact_ids_are_stable(self):
        """Same inputs always produce the same fact_id."""
        id1 = Fact.make_id("pdf", "go", "source", "api_class", "Doc")
        id2 = Fact.make_id("pdf", "go", "source", "api_class", "Doc")
        assert id1 == id2

    def test_empty_api_surface(self, tmp_path):
        merged = tmp_path / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("repo_sha: abc\n", encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        g = compile_fact_graph("pdf", "go", tmp_path)
        assert g.fact_count == 0


# ---------------------------------------------------------------------------
# Negative tests for product_state module
# ---------------------------------------------------------------------------

class TestProductStateNegative:
    def test_skip_phase_raises(self):
        """Cannot jump from DISCOVERED directly to FACTS_EXTRACTED."""
        state = ProductState(family="pdf", platform="go")
        with pytest.raises(IllegalTransitionError):
            state.transition(Phase.FACTS_EXTRACTED)

    def test_quarantined_cannot_self_heal(self):
        """Quarantined can only go to DISCOVERED."""
        state = ProductState(phase=Phase.QUARANTINED.value)
        with pytest.raises(IllegalTransitionError):
            state.transition(Phase.FACTS_VERIFIED)

    def test_negative_retry_count_invalid_in_schema(self):
        state = ProductState(family="pdf", platform="go", retry_count=-1)
        errors = validate_product_state(state.to_dict())
        assert any("retry_count" in e for e in errors)


# ---------------------------------------------------------------------------
# Negative tests for external_signals module
# ---------------------------------------------------------------------------

class TestExternalSignalsNegative:
    def test_advisory_forced_true(self):
        """ExternalSignal.__post_init__ forces advisory=True even if False is passed."""
        sig = ExternalSignal(signal_type="test", text="t", source="s", advisory=False)
        assert sig.advisory is True

    def test_frozen_signal(self):
        """ExternalSignal is frozen; attributes cannot be mutated."""
        sig = ExternalSignal(signal_type="test", text="t", source="s")
        with pytest.raises(AttributeError):
            sig.text = "modified"


# ---------------------------------------------------------------------------
# Sample output validation
# ---------------------------------------------------------------------------

class TestSampleOutputValidation:
    """Validate that generated sample outputs pass schema validation."""
    SAMPLES_DIR = Path(__file__).resolve().parents[1] / "reports" / "autonomous-content-tooling" / "ACT-MEGA-VERIFY-HARDEN-ADVANCE-20260606-001" / "samples"

    def test_fact_graph_sample(self):
        path = self.SAMPLES_DIR / "pdf_go_fact_graph.json"
        if not path.exists():
            pytest.skip("Sample not generated yet")
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_fact_graph(data)
        assert errors == [], f"Validation errors: {errors}"

    def test_page_plan_sample(self):
        path = self.SAMPLES_DIR / "pdf_go_page_plan.json"
        if not path.exists():
            pytest.skip("Sample not generated yet")
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_page_plan(data)
        assert errors == [], f"Validation errors: {errors}"

    def test_next_action_sample(self):
        path = self.SAMPLES_DIR / "next_action.json"
        if not path.exists():
            pytest.skip("Sample not generated yet")
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_next_action(data)
        assert errors == [], f"Validation errors: {errors}"

    def test_external_signals_sample(self):
        path = self.SAMPLES_DIR / "pdf_go_external_signals.json"
        if not path.exists():
            pytest.skip("Sample not generated yet")
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_external_signals(data)
        assert errors == [], f"Validation errors: {errors}"
