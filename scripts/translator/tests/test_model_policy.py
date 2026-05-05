"""
Tests for translator.preflight.model_policy

Verifies:
- Thinking model detection (positive and negative)
- Translation-suitability classification
- Unknown model handling
- TRANSLATE_ALLOW_THINKING_MODELS env var behaviour
- TRANSLATE_MODEL_BLOCKLIST env var behaviour
- select_best_model() selection logic
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from translator.preflight.model_policy import classify_model, select_best_model, ModelInfo


# ---------------------------------------------------------------------------
# Thinking model detection
# ---------------------------------------------------------------------------

class TestThinkingModelDetection:
    def test_o1_is_thinking(self):
        m = classify_model("o1-mini")
        assert m.is_thinking is True

    def test_o1_bare_is_thinking(self):
        m = classify_model("o1")
        assert m.is_thinking is True

    def test_o3_is_thinking(self):
        m = classify_model("o3-preview")
        assert m.is_thinking is True

    def test_deepseek_r1_is_thinking(self):
        m = classify_model("deepseek-r1")
        assert m.is_thinking is True

    def test_deepseek_r1_distill_is_thinking(self):
        m = classify_model("deepseek-r1-distill-qwen-7b")
        assert m.is_thinking is True

    def test_thinking_suffix_is_thinking(self):
        m = classify_model("qwen3-14b-thinking")
        assert m.is_thinking is True

    def test_with_thinking_variant(self):
        m = classify_model("claude-3-7-sonnet-with-thinking")
        assert m.is_thinking is True

    def test_qwq_is_thinking(self):
        m = classify_model("qwq-32b")
        assert m.is_thinking is True

    def test_r1_prefix(self):
        m = classify_model("r1-lite-preview")
        assert m.is_thinking is True

    def test_gpt_oss_is_not_thinking(self):
        m = classify_model("gpt-oss")
        assert m.is_thinking is False

    def test_llama3_is_not_thinking(self):
        m = classify_model("llama3.2")
        assert m.is_thinking is False

    def test_mistral_is_not_thinking(self):
        m = classify_model("mistral-7b")
        assert m.is_thinking is False

    def test_m2m100_is_not_thinking(self):
        m = classify_model("facebook/m2m100_418m")
        assert m.is_thinking is False

    def test_qwen2_is_not_thinking(self):
        # qwen2 (not qwq) should not be thinking
        m = classify_model("qwen2.5-7b")
        assert m.is_thinking is False


# ---------------------------------------------------------------------------
# Translation suitability
# ---------------------------------------------------------------------------

class TestTranslationSuitability:
    def test_gpt_oss_is_suitable(self):
        m = classify_model("gpt-oss")
        assert m.is_translation_suitable is True

    def test_llama3_is_suitable(self):
        m = classify_model("llama3.2:latest")
        assert m.is_translation_suitable is True

    def test_mistral_is_suitable(self):
        m = classify_model("mistral-nemo")
        assert m.is_translation_suitable is True

    def test_m2m100_is_suitable(self):
        m = classify_model("facebook/m2m100_418m")
        assert m.is_translation_suitable is True

    def test_thinking_model_not_suitable_by_default(self):
        m = classify_model("deepseek-r1")
        assert m.is_translation_suitable is False

    def test_unknown_model_is_suitable(self):
        # Unknown models assumed suitable (permissive default)
        m = classify_model("some-custom-model-v3")
        assert m.is_translation_suitable is True
        assert "Unknown" in m.reason or "unknown" in m.reason.lower() or "assumed" in m.reason

    def test_unknown_model_is_not_thinking(self):
        m = classify_model("some-custom-model-v3")
        assert m.is_thinking is False


# ---------------------------------------------------------------------------
# TRANSLATE_ALLOW_THINKING_MODELS env var
# ---------------------------------------------------------------------------

class TestAllowThinkingModels:
    def test_thinking_model_allowed_when_env_set(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_ALLOW_THINKING_MODELS", "1")
        m = classify_model("deepseek-r1")
        assert m.is_thinking is True
        assert m.is_translation_suitable is True

    def test_thinking_model_blocked_by_default(self, monkeypatch):
        monkeypatch.delenv("TRANSLATE_ALLOW_THINKING_MODELS", raising=False)
        m = classify_model("deepseek-r1")
        assert m.is_translation_suitable is False

    def test_thinking_model_blocked_when_env_zero(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_ALLOW_THINKING_MODELS", "0")
        m = classify_model("o1-mini")
        assert m.is_translation_suitable is False


# ---------------------------------------------------------------------------
# TRANSLATE_MODEL_BLOCKLIST env var
# ---------------------------------------------------------------------------

class TestModelBlocklist:
    def test_custom_blocklist_blocks_model(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_MODEL_BLOCKLIST", "my-internal-model")
        m = classify_model("my-internal-model-v2")
        assert m.is_thinking is True
        assert m.is_translation_suitable is False

    def test_blocklist_does_not_affect_other_models(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_MODEL_BLOCKLIST", "my-internal-model")
        m = classify_model("llama3.2")
        assert m.is_thinking is False
        assert m.is_translation_suitable is True

    def test_empty_blocklist_has_no_effect(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_MODEL_BLOCKLIST", "")
        m = classify_model("gpt-oss")
        assert m.is_translation_suitable is True


# ---------------------------------------------------------------------------
# select_best_model()
# ---------------------------------------------------------------------------

class TestSelectBestModel:
    def test_empty_list_returns_none(self):
        assert select_best_model([]) is None

    def test_selects_known_suitable_model(self):
        models = [{"id": "gpt-oss"}, {"id": "some-unknown"}]
        best = select_best_model(models)
        assert best is not None
        assert best.model_id == "gpt-oss"

    def test_respects_preferred_id(self):
        models = [{"id": "gpt-oss"}, {"id": "llama3.2"}]
        best = select_best_model(models, preferred_id="llama3.2")
        assert best is not None
        assert best.model_id == "llama3.2"

    def test_preferred_id_with_tag_suffix(self):
        # "llama3.2" preferred should match "llama3.2:latest"
        models = [{"id": "llama3.2:latest"}]
        best = select_best_model(models, preferred_id="llama3.2")
        assert best is not None
        assert best.model_id == "llama3.2:latest"

    def test_does_not_select_thinking_model_by_default(self, monkeypatch):
        monkeypatch.delenv("TRANSLATE_ALLOW_THINKING_MODELS", raising=False)
        models = [{"id": "deepseek-r1"}, {"id": "o1-mini"}]
        best = select_best_model(models)
        assert best is None

    def test_selects_thinking_model_when_allowed(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_ALLOW_THINKING_MODELS", "1")
        models = [{"id": "deepseek-r1"}]
        best = select_best_model(models)
        assert best is not None
        assert best.model_id == "deepseek-r1"

    def test_unknown_model_selected_when_only_option(self):
        models = [{"id": "custom-translate-model-v1"}]
        best = select_best_model(models)
        assert best is not None
        assert best.model_id == "custom-translate-model-v1"
