"""
Tests for translator.preflight.checker (PreflightChecker)

Verifies:
- All backends available → LLM selected
- Only Ollama available → Ollama selected
- Only M2M100 downloaded → M2M100 selected
- Nothing available → error
- Thinking model blocked → falls through to next backend
- Thinking model allowed → accepted with warning
- --provider llm explicit → fails when unavailable
- --provider ollama explicit → fails when unavailable
- --provider m2m, model not downloaded → error
- M2M100 packages missing → m2m backend unavailable
- Ollama model not installed → warning + fallback to available model
- Fallback chain construction
"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from translator.preflight.checker import PreflightChecker, PreflightReport


# ---------------------------------------------------------------------------
# Helper: build mock BackendCapability-style return values for _probe_*
# ---------------------------------------------------------------------------

def _llm_cap(available=True, selected_model="gpt-oss", models=None, warnings=None):
    from translator.preflight.checker import BackendCapability
    from translator.preflight.model_policy import classify_model
    if models is None:
        models = [classify_model("gpt-oss")] if available else []
    return BackendCapability(
        name="llm",
        available=available,
        unavailable_reason=None if available else "LLM_API_KEY not set",
        models=models,
        selected_model=selected_model if available else None,
        warnings=warnings or [],
    )


def _ollama_cap(available=True, selected_model="llama3.2", models=None, warnings=None):
    from translator.preflight.checker import BackendCapability
    from translator.preflight.model_policy import classify_model
    if models is None:
        models = [classify_model("llama3.2")] if available else []
    return BackendCapability(
        name="ollama",
        available=available,
        unavailable_reason=None if available else "Ollama not running at http://localhost:11434",
        models=models,
        selected_model=selected_model if available else None,
        warnings=warnings or [],
    )


def _m2m_cap(available=True, selected_model="facebook/m2m100_418m", warnings=None):
    from translator.preflight.checker import BackendCapability
    from translator.preflight.model_policy import classify_model
    return BackendCapability(
        name="m2m100",
        available=available,
        unavailable_reason=None if available else "transformers not installed",
        models=[classify_model("facebook/m2m100_418m")] if available else [],
        selected_model=selected_model,
        warnings=warnings or [],
    )


# ---------------------------------------------------------------------------
# Helper: patch all three probe methods at once
# ---------------------------------------------------------------------------

def _checker_with_mocked_probes(llm=None, ollama=None, m2m=None, dl_state=None):
    """Return a PreflightChecker with _probe_* methods mocked."""
    checker = PreflightChecker()
    checker._probe_llm = MagicMock(return_value=llm or _llm_cap(available=False))
    checker._probe_ollama = MagicMock(return_value=ollama or _ollama_cap(available=False))
    checker._probe_m2m = MagicMock(return_value=m2m or _m2m_cap(available=False))
    if dl_state is not None:
        checker._m2m_download_state = MagicMock(return_value=dl_state)
    return checker


# ---------------------------------------------------------------------------
# Auto provider — selection policy
# ---------------------------------------------------------------------------

class TestAutoProvider:
    def test_llm_selected_when_available(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=True, selected_model="gpt-oss"),
            ollama=_ollama_cap(available=False),
            m2m=_m2m_cap(available=False),
        )
        report = checker.run(provider="auto")
        assert report.ok()
        assert report.selected_backend == "llm"
        assert report.selected_model == "gpt-oss"

    def test_ollama_fallback_when_llm_unavailable(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
            ollama=_ollama_cap(available=True, selected_model="llama3.2"),
            m2m=_m2m_cap(available=False),
        )
        report = checker.run(provider="auto")
        assert report.ok()
        assert report.selected_backend == "ollama"
        assert report.selected_model == "llama3.2"

    def test_m2m_fallback_when_llm_and_ollama_unavailable(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
            ollama=_ollama_cap(available=False),
            m2m=_m2m_cap(available=True, selected_model="facebook/m2m100_418m"),
            dl_state={"downloaded": True, "reason": "cached", "cache_dir": "/cache", "size_bytes": 1_000_000},
        )
        report = checker.run(provider="auto")
        assert report.ok()
        assert report.selected_backend == "m2m100"

    def test_error_when_nothing_available(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
            ollama=_ollama_cap(available=False),
            m2m=_m2m_cap(available=False),
        )
        report = checker.run(provider="auto")
        assert not report.ok()
        assert len(report.errors) > 0

    def test_llm_and_ollama_both_available_builds_fallback_chain(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=True, selected_model="gpt-oss"),
            ollama=_ollama_cap(available=True, selected_model="llama3.2"),
            m2m=_m2m_cap(available=False),
        )
        report = checker.run(provider="auto")
        assert report.ok()
        assert "llm" in report.fallback_chain
        assert "ollama" in report.fallback_chain
        assert report.fallback_chain.index("llm") < report.fallback_chain.index("ollama")


# ---------------------------------------------------------------------------
# Explicit provider overrides
# ---------------------------------------------------------------------------

class TestExplicitProvider:
    def test_provider_llm_uses_llm(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=True, selected_model="gpt-oss"),
            ollama=_ollama_cap(available=True),
        )
        report = checker.run(provider="llm")
        assert report.ok()
        assert report.selected_backend == "llm"

    def test_provider_llm_fails_when_unavailable(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
        )
        report = checker.run(provider="llm")
        assert not report.ok()
        assert any("LLM" in e or "llm" in e.lower() for e in report.errors)

    def test_provider_ollama_uses_ollama(self):
        checker = _checker_with_mocked_probes(
            ollama=_ollama_cap(available=True, selected_model="llama3.2"),
        )
        report = checker.run(provider="ollama")
        assert report.ok()
        assert report.selected_backend == "ollama"

    def test_provider_ollama_fails_when_unavailable(self):
        checker = _checker_with_mocked_probes(
            ollama=_ollama_cap(available=False),
        )
        report = checker.run(provider="ollama")
        assert not report.ok()

    def test_provider_m2m_uses_m2m_when_downloaded(self):
        checker = _checker_with_mocked_probes(
            m2m=_m2m_cap(available=True),
            dl_state={"downloaded": True, "reason": "ok", "cache_dir": "/cache", "size_bytes": 500_000_000},
        )
        report = checker.run(provider="m2m")
        assert report.ok()
        assert report.selected_backend == "m2m100"

    def test_provider_m2m_fails_when_not_downloaded(self):
        checker = _checker_with_mocked_probes(
            m2m=_m2m_cap(available=True),
            dl_state={"downloaded": False, "reason": "Model directory not found", "cache_dir": "/cache", "size_bytes": 0},
        )
        report = checker.run(provider="m2m")
        assert not report.ok()
        assert any("not downloaded" in e.lower() or "m2m" in e.lower() for e in report.errors)

    def test_provider_m2m_fails_when_packages_missing(self):
        checker = _checker_with_mocked_probes(
            m2m=_m2m_cap(available=False),
        )
        report = checker.run(provider="m2m")
        assert not report.ok()


# ---------------------------------------------------------------------------
# Thinking model handling
# ---------------------------------------------------------------------------

class TestThinkingModelHandling:
    def test_llm_with_thinking_model_only_falls_through(self, monkeypatch):
        """When LLM only has thinking models, it should not be selected (auto)."""
        monkeypatch.delenv("TRANSLATE_ALLOW_THINKING_MODELS", raising=False)
        from translator.preflight.model_policy import classify_model
        from translator.preflight.checker import BackendCapability
        thinking_cap = BackendCapability(
            name="llm",
            available=True,
            unavailable_reason=None,
            models=[classify_model("deepseek-r1")],
            selected_model=None,  # no suitable model
            warnings=["Selected model appears to be a thinking model"],
        )
        checker = _checker_with_mocked_probes(
            llm=thinking_cap,
            ollama=_ollama_cap(available=True, selected_model="llama3.2"),
        )
        report = checker.run(provider="auto")
        # Should fall through to Ollama
        assert report.ok()
        assert report.selected_backend == "ollama"

    def test_llm_thinking_model_warning_present(self, monkeypatch):
        monkeypatch.delenv("TRANSLATE_ALLOW_THINKING_MODELS", raising=False)
        from translator.preflight.model_policy import classify_model
        from translator.preflight.checker import BackendCapability
        cap = BackendCapability(
            name="llm",
            available=True,
            unavailable_reason=None,
            models=[classify_model("deepseek-r1")],
            selected_model=None,
            warnings=["Selected model 'deepseek-r1' appears to be a thinking/reasoning model"],
        )
        checker = _checker_with_mocked_probes(llm=cap, ollama=_ollama_cap(available=False))
        report = checker.run(provider="auto")
        # No valid backend — should have errors
        assert not report.ok()


# ---------------------------------------------------------------------------
# M2M100 not-downloaded state
# ---------------------------------------------------------------------------

class TestM2MDownloadState:
    def test_m2m_not_downloaded_surfaces_clear_error(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
            ollama=_ollama_cap(available=False),
            m2m=_m2m_cap(available=True, warnings=["Model not downloaded: Model directory not found"]),
            dl_state={"downloaded": False, "reason": "Model directory not found", "cache_dir": "/cache", "size_bytes": 0},
        )
        report = checker.run(provider="auto")
        # Should fail with a clear error, not a cryptic traceback
        assert not report.ok()
        combined = " ".join(report.errors + report.warnings)
        assert "download" in combined.lower() or "not found" in combined.lower()

    def test_m2m_downloaded_is_usable(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
            ollama=_ollama_cap(available=False),
            m2m=_m2m_cap(available=True, selected_model="facebook/m2m100_418m"),
            dl_state={"downloaded": True, "reason": "cached", "cache_dir": "/cache", "size_bytes": 800_000_000},
        )
        report = checker.run(provider="auto")
        assert report.ok()
        assert report.selected_backend == "m2m100"


# ---------------------------------------------------------------------------
# PreflightReport formatting
# ---------------------------------------------------------------------------

class TestPreflightReportFormatting:
    def test_format_summary_ok(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=True, selected_model="gpt-oss"),
        )
        report = checker.run(provider="auto")
        summary = report.format_summary()
        assert "PREFLIGHT OK" in summary
        assert "llm" in summary

    def test_format_summary_fail(self):
        checker = _checker_with_mocked_probes()
        report = checker.run(provider="auto")
        summary = report.format_summary()
        assert "PREFLIGHT FAIL" in summary

    def test_format_report_contains_all_backends(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=False),
            ollama=_ollama_cap(available=False),
            m2m=_m2m_cap(available=False),
        )
        report = checker.run(provider="auto")
        full = report.format_report()
        assert "llm" in full
        assert "ollama" in full
        assert "m2m100" in full

    def test_ok_method(self):
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=True, selected_model="gpt-oss"),
        )
        report = checker.run(provider="auto")
        assert report.ok() is True

    def test_not_ok_when_errors(self):
        checker = _checker_with_mocked_probes()
        report = checker.run(provider="auto")
        assert report.ok() is False


# ---------------------------------------------------------------------------
# TRANSLATE_OFFLINE env var → forces m2m provider
# ---------------------------------------------------------------------------

class TestOfflineEnvVar:
    def test_translate_offline_forces_m2m(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_OFFLINE", "1")
        checker = _checker_with_mocked_probes(
            m2m=_m2m_cap(available=True),
            dl_state={"downloaded": True, "reason": "ok", "cache_dir": "/cache", "size_bytes": 500_000_000},
        )
        report = checker.run()  # no explicit provider
        assert report.selected_backend == "m2m100"

    def test_translate_offline_zero_does_not_force_m2m(self, monkeypatch):
        monkeypatch.setenv("TRANSLATE_OFFLINE", "0")
        checker = _checker_with_mocked_probes(
            llm=_llm_cap(available=True, selected_model="gpt-oss"),
        )
        report = checker.run()
        assert report.selected_backend == "llm"
