"""
PreflightChecker — probes all translation backends before any work starts.

Responsibilities:
  1. Probe each backend for availability
  2. List available models
  3. Classify models (thinking vs non-thinking, suitability)
  4. Apply selection policy to choose best backend/model
  5. Return a PreflightReport describing the result

Usage:
    from translator.preflight import PreflightChecker
    report = PreflightChecker().run(provider="auto")
    print(report.format_summary())
    if report.errors:
        sys.exit(1)

Provider values:
    "auto"    — default, tries llm → ollama → m2m100 in order
    "llm"     — force llm.professionalize.com (fail if unavailable)
    "ollama"  — force local Ollama (fail if unavailable)
    "m2m"     — force M2M100 offline (fail if not downloaded)

Environment variables honoured:
    TRANSLATE_PROVIDER              — default provider (overridden by run(provider=...))
    TRANSLATE_ALLOW_THINKING_MODELS — allow thinking models when 1
    TRANSLATE_MODEL_BLOCKLIST       — extra blocklist patterns
    LLM_API_KEY                     — required for llm backend
    TRANSLATE_PRIMARY_MODEL         — preferred LLM model
    TRANSLATE_OLLAMA_MODEL          — preferred Ollama model
    TRANSLATE_OFFLINE               — if "1", forces provider="m2m"
"""
from __future__ import annotations
import datetime
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from translator.preflight.model_policy import ModelInfo, classify_model, select_best_model

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ("auto", "llm", "ollama", "m2m")


@dataclass
class BackendCapability:
    """Probed capability result for one translation backend."""
    name: str                           # "llm", "ollama", "m2m100"
    available: bool
    unavailable_reason: Optional[str]   # set when available=False
    models: list[ModelInfo]             # empty if unavailable or cannot list
    selected_model: Optional[str]       # best model_id for this backend
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreflightReport:
    """
    Complete preflight result.

    errors   — non-empty means no valid backend; translation must not start
    warnings — non-fatal issues to display before translation starts
    fallback_chain — ordered backend names to pass to BackendRouter
    """
    backends: list[BackendCapability]
    selected_backend: Optional[str]     # "llm", "ollama", "m2m100", or None
    selected_model: Optional[str]
    selection_reason: str
    fallback_chain: list[str]           # e.g. ["llm", "ollama"]
    warnings: list[str]
    errors: list[str]
    timestamp: str

    def ok(self) -> bool:
        """Return True when preflight passed and translation can start."""
        return len(self.errors) == 0

    def format_summary(self) -> str:
        """Return a concise single-line status string."""
        if self.errors:
            return f"[PREFLIGHT FAIL] {'; '.join(self.errors)}"
        model_str = f" ({self.selected_model})" if self.selected_model else ""
        warn_str = f" - {len(self.warnings)} warning(s)" if self.warnings else ""
        return f"[PREFLIGHT OK] backend={self.selected_backend}{model_str}{warn_str}"

    def format_report(self) -> str:
        """Return a multi-line human-readable report."""
        lines = [
            "=" * 60,
            "TRANSLATION PREFLIGHT REPORT",
            f"Timestamp : {self.timestamp}",
            "",
        ]

        for bc in self.backends:
            status = "AVAILABLE" if bc.available else "UNAVAILABLE"
            lines.append(f"  Backend : {bc.name}  [{status}]")
            if not bc.available and bc.unavailable_reason:
                lines.append(f"    Reason  : {bc.unavailable_reason}")
            if bc.models:
                lines.append(f"    Models  : {len(bc.models)} available")
                for m in bc.models[:10]:
                    tag = ""
                    if m.is_thinking:
                        tag = "  [THINKING - blocked]"
                    elif not m.is_translation_suitable:
                        tag = "  [not suitable]"
                    lines.append(f"      - {m.model_id}{tag}")
                if len(bc.models) > 10:
                    lines.append(f"      ... and {len(bc.models) - 10} more")
            if bc.selected_model:
                lines.append(f"    Selected: {bc.selected_model}")
            for w in bc.warnings:
                lines.append(f"    WARNING : {w}")
            lines.append("")

        lines.append(f"  Selection : backend={self.selected_backend}  model={self.selected_model}")
        lines.append(f"  Reason    : {self.selection_reason}")
        if self.fallback_chain:
            lines.append(f"  Fallback  : {' -> '.join(self.fallback_chain)}")
        if self.warnings:
            lines.append("")
            for w in self.warnings:
                lines.append(f"  WARN : {w}")
        if self.errors:
            lines.append("")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        lines.append("=" * 60)
        return "\n".join(lines)


class PreflightChecker:
    """
    Probe all translation backends and select the best one.

    Typical usage:
        checker = PreflightChecker()
        report = checker.run(provider="auto")
    """

    def run(self, provider: Optional[str] = None) -> PreflightReport:
        """
        Run preflight checks and return a PreflightReport.

        provider: "auto" | "llm" | "ollama" | "m2m" | None
          None → reads TRANSLATE_PROVIDER env var, defaults to "auto"
          "auto" → tries llm → ollama → m2m100 in priority order
          other values → force a single backend (error if unavailable)

        TRANSLATE_OFFLINE=1 is treated as provider="m2m" regardless.
        """
        # Resolve provider
        if os.environ.get("TRANSLATE_OFFLINE", "0").strip() == "1":
            provider = "m2m"
        if provider is None:
            provider = os.environ.get("TRANSLATE_PROVIDER", "auto").strip().lower()
        if provider not in VALID_PROVIDERS:
            provider = "auto"

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        global_warnings: list[str] = []
        global_errors: list[str] = []

        # Probe all backends
        llm_cap = self._probe_llm()
        ollama_cap = self._probe_ollama()
        m2m_cap = self._probe_m2m()

        backends = [llm_cap, ollama_cap, m2m_cap]

        # Apply selection policy
        selected_backend: Optional[str] = None
        selected_model: Optional[str] = None
        selection_reason = ""
        fallback_chain: list[str] = []

        if provider == "llm":
            if llm_cap.available and llm_cap.selected_model:
                selected_backend = "llm"
                selected_model = llm_cap.selected_model
                selection_reason = "Forced by --provider llm"
                fallback_chain = ["llm"]
            elif llm_cap.available and not llm_cap.selected_model:
                global_errors.append(
                    "LLM backend is reachable but no translation-suitable model found. "
                    "Set TRANSLATE_PRIMARY_MODEL to a non-thinking model or "
                    "set TRANSLATE_ALLOW_THINKING_MODELS=1."
                )
            else:
                global_errors.append(
                    f"LLM backend unavailable: {llm_cap.unavailable_reason}"
                )

        elif provider == "ollama":
            if ollama_cap.available and ollama_cap.selected_model:
                selected_backend = "ollama"
                selected_model = ollama_cap.selected_model
                selection_reason = "Forced by --provider ollama"
                fallback_chain = ["ollama"]
            elif ollama_cap.available and not ollama_cap.selected_model:
                global_errors.append(
                    "Ollama backend is running but no translation-suitable model found. "
                    f"Configured model: {os.environ.get('TRANSLATE_OLLAMA_MODEL', 'llama3.2')}. "
                    "Run: ollama pull <model>"
                )
            else:
                global_errors.append(
                    f"Ollama backend unavailable: {ollama_cap.unavailable_reason}"
                )

        elif provider == "m2m":
            if m2m_cap.available:
                # Check download state separately
                dl = self._m2m_download_state()
                if dl["downloaded"]:
                    selected_backend = "m2m100"
                    selected_model = "facebook/m2m100_418m"
                    selection_reason = "Forced by --provider m2m (model downloaded)"
                    fallback_chain = ["m2m100"]
                else:
                    global_errors.append(
                        f"M2M100 not downloaded: {dl['reason']}"
                    )
            else:
                global_errors.append(
                    "M2M100 backend unavailable: transformers and/or torch not installed. "
                    "Install with: pip install transformers torch"
                )

        else:  # auto
            # Priority: llm → ollama → m2m100
            if llm_cap.available and llm_cap.selected_model:
                selected_backend = "llm"
                selected_model = llm_cap.selected_model
                selection_reason = "Auto-selected: LLM backend available with suitable model"
                fallback_chain = ["llm"]
                if ollama_cap.available and ollama_cap.selected_model:
                    fallback_chain.append("ollama")
            elif ollama_cap.available and ollama_cap.selected_model:
                selected_backend = "ollama"
                selected_model = ollama_cap.selected_model
                if llm_cap.available:
                    selection_reason = "Auto-selected: LLM available but no suitable model; using Ollama"
                else:
                    selection_reason = f"Auto-selected: LLM unavailable ({llm_cap.unavailable_reason}); using Ollama"
                fallback_chain = ["ollama"]
            elif m2m_cap.available:
                dl = self._m2m_download_state()
                if dl["downloaded"]:
                    selected_backend = "m2m100"
                    selected_model = "facebook/m2m100_418m"
                    selection_reason = (
                        "Auto-selected: LLM and Ollama unavailable; using local M2M100"
                    )
                    fallback_chain = ["m2m100"]
                else:
                    global_errors.append(
                        "No usable backend found. "
                        "LLM: not configured or unreachable. "
                        "Ollama: not running or no suitable model. "
                        f"M2M100: not downloaded ({dl['reason']})."
                    )
            else:
                msgs = []
                if not llm_cap.available:
                    msgs.append(f"LLM: {llm_cap.unavailable_reason}")
                elif not llm_cap.selected_model:
                    msgs.append("LLM: no suitable translation model available")
                if not ollama_cap.available:
                    msgs.append(f"Ollama: {ollama_cap.unavailable_reason}")
                elif not ollama_cap.selected_model:
                    msgs.append("Ollama: no suitable model installed")
                if not m2m_cap.available:
                    msgs.append("M2M100: transformers/torch not installed")
                global_errors.append(
                    "No usable translation backend found. " + " | ".join(msgs)
                )

        # Collect all backend warnings into global warnings
        for bc in backends:
            for w in bc.warnings:
                global_warnings.append(f"[{bc.name}] {w}")

        return PreflightReport(
            backends=backends,
            selected_backend=selected_backend,
            selected_model=selected_model,
            selection_reason=selection_reason,
            fallback_chain=fallback_chain,
            warnings=global_warnings,
            errors=global_errors,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Backend probing helpers
    # ------------------------------------------------------------------

    def _probe_llm(self) -> BackendCapability:
        """Probe the LLM (llm.professionalize.com) backend."""
        warnings: list[str] = []
        api_key = os.environ.get("LLM_API_KEY", "").strip()
        if not api_key:
            return BackendCapability(
                name="llm",
                available=False,
                unavailable_reason="LLM_API_KEY environment variable is not set",
                models=[],
                selected_model=None,
                warnings=[],
            )
        try:
            from translator.backends.llm import LLMBackend
            backend = LLMBackend()
        except Exception as exc:
            return BackendCapability(
                name="llm",
                available=False,
                unavailable_reason=f"LLMBackend init failed: {exc}",
                models=[],
                selected_model=None,
                warnings=[],
            )

        if not backend.is_available():
            return BackendCapability(
                name="llm",
                available=False,
                unavailable_reason=f"Endpoint not reachable: {backend.base_url}",
                models=[],
                selected_model=None,
                warnings=[],
            )

        # List models
        raw_models = backend.list_models()
        preferred = os.environ.get("TRANSLATE_PRIMARY_MODEL", "").strip()

        if not raw_models:
            warnings.append(
                "Could not list models from /models endpoint (auth issue or non-standard API). "
                f"Will use configured model: {preferred or 'recommended'}"
            )
            # Fall back to the configured model name
            fallback_model = preferred or "recommended"
            mi = classify_model(fallback_model)
            models = [mi]
        else:
            models = [classify_model(m["id"]) for m in raw_models]

        best = select_best_model(
            [{"id": m.model_id} for m in models],
            preferred_id=preferred or None,
        )

        if best and best.is_thinking:
            warnings.append(
                f"Configured model '{best.model_id}' appears to be a thinking/reasoning model. "
                "Searching for a non-thinking alternative."
            )
            # Try to find a non-thinking alternative from available models
            alternative = select_best_model([{"id": m.model_id} for m in models])
            if alternative and alternative.is_translation_suitable and not alternative.is_thinking:
                warnings.append(
                    f"Auto-selected '{alternative.model_id}' as non-thinking alternative. "
                    "Set TRANSLATE_PRIMARY_MODEL to override, or TRANSLATE_ALLOW_THINKING_MODELS=1 to use thinking models."
                )
                best = alternative
            else:
                warnings.append(
                    "No non-thinking translation-suitable model found. "
                    "Change TRANSLATE_PRIMARY_MODEL or set TRANSLATE_ALLOW_THINKING_MODELS=1."
                )

        if best and not best.is_translation_suitable:
            return BackendCapability(
                name="llm",
                available=True,
                unavailable_reason=None,
                models=models,
                selected_model=None,
                warnings=warnings + [
                    f"No translation-suitable model found. Best candidate '{best.model_id}': {best.reason}"
                ],
            )

        return BackendCapability(
            name="llm",
            available=True,
            unavailable_reason=None,
            models=models,
            selected_model=best.model_id if best else None,
            warnings=warnings,
        )

    def _probe_ollama(self) -> BackendCapability:
        """Probe the local Ollama backend."""
        warnings: list[str] = []
        try:
            from translator.backends.ollama import OllamaBackend
            backend = OllamaBackend()
        except Exception as exc:
            return BackendCapability(
                name="ollama",
                available=False,
                unavailable_reason=f"OllamaBackend init failed: {exc}",
                models=[],
                selected_model=None,
                warnings=[],
            )

        if not backend.is_available():
            return BackendCapability(
                name="ollama",
                available=False,
                unavailable_reason=f"Ollama not running at {backend.base_url}",
                models=[],
                selected_model=None,
                warnings=[],
            )

        raw_models = backend.list_models()
        configured_model = os.environ.get("TRANSLATE_OLLAMA_MODEL", "llama3.2").strip()

        if not raw_models:
            warnings.append(
                "Ollama is running but no models are installed. "
                f"Run: ollama pull {configured_model}"
            )
            return BackendCapability(
                name="ollama",
                available=True,
                unavailable_reason=None,
                models=[],
                selected_model=None,
                warnings=warnings,
            )

        models = [classify_model(m["id"]) for m in raw_models]

        # Check if configured model is actually installed
        if not backend.is_model_installed(configured_model):
            installed_names = [m["id"] for m in raw_models]
            warnings.append(
                f"Configured model '{configured_model}' is not installed in Ollama. "
                f"Installed: {', '.join(installed_names[:5])}{'...' if len(installed_names) > 5 else ''}. "
                f"Run: ollama pull {configured_model}"
            )
            # Try to select from installed models instead
            best = select_best_model([{"id": m.model_id} for m in models])
        else:
            best = select_best_model(
                [{"id": m.model_id} for m in models],
                preferred_id=configured_model,
            )

        if best and best.is_thinking:
            warnings.append(
                f"Configured Ollama model '{best.model_id}' appears to be a thinking model. "
                "Searching for a non-thinking alternative from installed models."
            )
            # Try to find a non-thinking alternative
            alternative = select_best_model([{"id": m.model_id} for m in models])
            if alternative and alternative.is_translation_suitable and not alternative.is_thinking:
                warnings.append(
                    f"Auto-selected '{alternative.model_id}' as non-thinking alternative. "
                    "Set TRANSLATE_OLLAMA_MODEL to override, or TRANSLATE_ALLOW_THINKING_MODELS=1 to use thinking models."
                )
                best = alternative
            else:
                warnings.append(
                    "No non-thinking translation-suitable model found in Ollama. "
                    "Install a suitable model (e.g. ollama pull llama3.2) or set TRANSLATE_ALLOW_THINKING_MODELS=1."
                )

        selected = best.model_id if (best and best.is_translation_suitable) else None

        return BackendCapability(
            name="ollama",
            available=True,
            unavailable_reason=None,
            models=models,
            selected_model=selected,
            warnings=warnings,
        )

    def _probe_m2m(self) -> BackendCapability:
        """Probe the M2M100 offline backend (checks packages only; download check is separate)."""
        try:
            from translator.backends.m2m import M2MBackend
            backend = M2MBackend()
        except Exception as exc:
            return BackendCapability(
                name="m2m100",
                available=False,
                unavailable_reason=f"M2MBackend init failed: {exc}",
                models=[],
                selected_model=None,
                warnings=[],
            )

        if not backend.is_available():
            return BackendCapability(
                name="m2m100",
                available=False,
                unavailable_reason=(
                    "transformers and/or torch not installed. "
                    "Install with: pip install transformers torch"
                ),
                models=[],
                selected_model=None,
                warnings=[],
            )

        dl = backend.check_download_state()
        mi = classify_model("facebook/m2m100_418m")
        warnings: list[str] = []

        if not dl["downloaded"]:
            warnings.append(
                f"Model not downloaded: {dl['reason']}"
            )

        return BackendCapability(
            name="m2m100",
            available=True,
            unavailable_reason=None,
            models=[mi],
            selected_model="facebook/m2m100_418m" if dl["downloaded"] else None,
            warnings=warnings,
        )

    def _m2m_download_state(self) -> dict:
        """Return M2M100 download state dict."""
        try:
            from translator.backends.m2m import M2MBackend
            return M2MBackend().check_download_state()
        except Exception as exc:
            return {"downloaded": False, "reason": str(exc)}
