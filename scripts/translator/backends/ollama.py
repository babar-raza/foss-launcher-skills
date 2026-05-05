"""
OllamaBackend: local Ollama fallback backend.

Configuration:
  TRANSLATE_OLLAMA_BASE_URL   Optional. Default: http://localhost:11434
  TRANSLATE_OLLAMA_MODEL      Optional. Default: llama3.2

Auto-detected: if Ollama is not running, is_available() returns False and
BackendRouter will skip this backend.
"""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import BackendUnavailableError
from translator.backends.base import (
    TranslationBackend,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    _retry_with_backoff,
)

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "llama3.2"

OLLAMA_SYSTEM_PROMPT = """\
You are a professional technical translator. Translate the following from {src_lang_name} to {tgt_lang_name}.
Output ONLY the translation. No explanations. Preserve markdown, shortcodes, code, and API names exactly."""


class OllamaBackend(TranslationBackend):
    """
    Translation backend using a local Ollama instance.
    Used as fallback when the primary LLM backend is unavailable.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.base_url = (
            base_url or os.environ.get("TRANSLATE_OLLAMA_BASE_URL", _DEFAULT_OLLAMA_URL)
        ).rstrip("/")
        self.model = model or os.environ.get("TRANSLATE_OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if Ollama is running at the configured URL."""
        if self._available is not None:
            return self._available
        self._fetch_tags()
        return self._available

    def _fetch_tags(self) -> None:
        """Fetch and cache the /api/tags response. Sets _available and _tags_cache."""
        if hasattr(self, "_tags_cache"):
            return
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                self._available = True
                self._tags_cache = resp.json()
            else:
                self._available = False
                self._tags_cache = {}
        except Exception:
            self._available = False
            self._tags_cache = {}

    def list_models(self) -> list[dict]:
        """
        Return locally installed Ollama models.
        Parses the /api/tags response (cached from is_available()).
        Each dict has {"id": str} where id is the model name tag.
        """
        self._fetch_tags()
        models_raw = self._tags_cache.get("models", []) if isinstance(self._tags_cache, dict) else []
        return [{"id": m["name"]} for m in models_raw if isinstance(m, dict) and "name" in m]

    def is_model_installed(self, model_name: str) -> bool:
        """
        Return True if a model with the given name is in the local Ollama registry.
        Matches on exact name or name prefix (before ':').
        E.g., 'llama3.2' matches 'llama3.2:latest'.
        """
        installed = [m["id"] for m in self.list_models()]
        if model_name in installed:
            return True
        # Also match without tag suffix: 'llama3.2' should match 'llama3.2:latest'
        base = model_name.split(":")[0]
        for name in installed:
            if name.split(":")[0] == base:
                return True
        return False

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        if not self.is_available():
            raise BackendUnavailableError(f"Ollama not available at {self.base_url}")

        from translator import LOCALE_NAMES

        src_name = LOCALE_NAMES.get(src_lang, src_lang.upper())
        tgt_name = LOCALE_NAMES.get(tgt_lang, tgt_lang.upper())

        system = OLLAMA_SYSTEM_PROMPT.format(
            src_lang_name=src_name, tgt_lang_name=tgt_name
        )

        def _call():
            try:
                resp = self._session.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": text},
                        ],
                        "stream": False,
                        "options": {"temperature": self.temperature},
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    return resp.json()["message"]["content"].strip()
                else:
                    raise BackendUnavailableError(f"Ollama HTTP {resp.status_code}")
            except requests.exceptions.ConnectionError as e:
                self._available = False
                raise BackendUnavailableError(f"Ollama connection failed: {e}") from e
            except requests.exceptions.Timeout as e:
                raise BackendUnavailableError(f"Ollama timed out: {e}") from e

        return _retry_with_backoff(_call, self.max_retries)

    def get_model_info(self) -> dict:
        return {"backend": "ollama", "model": self.model, "url": self.base_url}
