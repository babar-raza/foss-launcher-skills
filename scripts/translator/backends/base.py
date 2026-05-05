"""
TranslationBackend ABC and BackendRouter.

All translation backends implement TranslationBackend.
BackendRouter tries primary → fallback chain with logging.
"""
from __future__ import annotations
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import BackendUnavailableError, ConfigurationError

logger = logging.getLogger(__name__)

# Default temperature for deterministic output
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TIMEOUT = int(os.environ.get("TRANSLATE_TIMEOUT", "30"))
DEFAULT_MAX_RETRIES = 3


class TranslationBackend(ABC):
    """Abstract base for all translation backends."""

    @abstractmethod
    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """Translate a single text segment. Returns translated string."""

    def translate_batch(self, texts: list[str], src_lang: str, tgt_lang: str) -> list[str]:
        """
        Translate a batch of text segments.
        Default implementation calls translate() sequentially.
        Subclasses should override with batched LLM calls for efficiency.
        """
        return [self.translate(t, src_lang, tgt_lang) for t in texts]

    @abstractmethod
    def get_model_info(self) -> dict:
        """Return backend name and model identifier."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is reachable/configured."""

    def list_models(self) -> list[dict]:
        """
        Return models available on this backend.
        Each dict has at minimum {"id": str}.
        Returns empty list if unavailable or not supported.
        Subclasses should override for real model enumeration.
        """
        return []

    def check_download_state(self) -> dict:
        """
        Return download/install state for offline backends.
        Default: {"downloaded": True, "reason": "not applicable"}.
        M2MBackend overrides this to inspect the HF cache.
        """
        return {"downloaded": True, "reason": "not applicable"}


class BackendRouter:
    """
    Routes translation requests through a priority chain of backends.
    Tries primary first; falls back to each subsequent backend on BackendUnavailableError.
    """

    def __init__(self, backends: list[TranslationBackend]):
        if not backends:
            raise ConfigurationError("BackendRouter requires at least one backend")
        self.backends = backends
        self._active: Optional[TranslationBackend] = None

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        for backend in self.backends:
            try:
                result = backend.translate(text, src_lang, tgt_lang)
                self._active = backend
                return result
            except BackendUnavailableError as e:
                logger.warning(
                    f"Backend {backend.get_model_info()['backend']} unavailable: {e}; trying next"
                )
        raise BackendUnavailableError("All translation backends failed")

    def translate_batch(self, texts: list[str], src_lang: str, tgt_lang: str) -> list[str]:
        for backend in self.backends:
            try:
                result = backend.translate_batch(texts, src_lang, tgt_lang)
                self._active = backend
                return result
            except BackendUnavailableError as e:
                logger.warning(
                    f"Backend {backend.get_model_info()['backend']} unavailable for batch: {e}; trying next"
                )
        raise BackendUnavailableError("All translation backends failed for batch")

    def active_backend_info(self) -> Optional[dict]:
        return self._active.get_model_info() if self._active else None


def _retry_with_backoff(func, max_retries: int = DEFAULT_MAX_RETRIES, base_delay: float = 2.0):
    """Retry a function with exponential backoff. Raises last exception on exhaustion."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return func()
        except BackendUnavailableError as e:
            last_exc = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(f"Retry {attempt + 1}/{max_retries} after {delay}s")
                time.sleep(delay)
    raise last_exc
