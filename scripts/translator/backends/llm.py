"""
LLMBackend: translation via llm.professionalize.com (OpenAI-compatible).

Configuration via environment variables:
  LLM_API_KEY           Required. API key for llm.professionalize.com
  LLM_API_BASE_URL      Optional. Default: https://llm.professionalize.com/v1
  TRANSLATE_PRIMARY_MODEL   Optional. Default: recommended
  TRANSLATE_BULK_MODEL      Optional. Falls back to TRANSLATE_PRIMARY_MODEL

Usage:
  backend = LLMBackend()
  result = backend.translate("Hello world", "en", "fr")
"""
from __future__ import annotations
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import BackendUnavailableError, ConfigurationError
from translator.backends.base import (
    TranslationBackend,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    _retry_with_backoff,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://llm.professionalize.com/v1"
_DEFAULT_MODEL = "recommended"

# NOTE: quadruple-braced shortcode placeholders so that .format() produces
# the literal double-brace output {{< ... >}} and {{% ... %}} in the final string.
SYSTEM_PROMPT_TEMPLATE = """\
You are a professional technical translator. Translate the following from {src_lang_name} to {tgt_lang_name}.

Rules:
- Output ONLY the translation. No explanations, notes, or commentary.
- Preserve all formatting: markdown syntax, HTML tags, code blocks, links.
- Preserve all Hugo shortcodes exactly: {{{{< ... >}}}} and {{{{% ... %}}}}
- Keep all technical terms, brand names (Aspose), and API identifiers unchanged.
- Keep all archive/format names unchanged: ZIP, PDF, DOCX, PPTX, FBX, OBJ, GLTF, etc.
- Maintain the same tone and register as the source.
- Do not add, remove, or reorder content.
- Do not invent or fabricate content not present in the source text.
- Translate ALL text to {tgt_lang_name}. Do not leave any sentences in {src_lang_name}.
- Preserve markdown heading levels (##, ###, etc.) exactly as in the source.
- Preserve table structure: same number of rows and columns as the source.
- Preserve blockquotes (lines starting with >) exactly as structured in the source.{context_block}"""

BATCH_SYSTEM_PROMPT_TEMPLATE = """\
You are a professional technical translator. Translate each numbered item from {src_lang_name} to {tgt_lang_name}.

Rules:
- Output ONLY the translations, keeping the same numbering format (1., 2., 3., etc.)
- No explanations, notes, or commentary — only the translated numbered list.
- Preserve all formatting: markdown syntax, HTML tags, code blocks, links.
- Preserve all Hugo shortcodes exactly: {{{{< ... >}}}} and {{{{% ... %}}}}
- Keep all technical terms, brand names (Aspose), and API identifiers unchanged.
- Keep all archive/format names unchanged: ZIP, PDF, DOCX, PPTX, FBX, OBJ, GLTF, etc.
- Maintain the same tone and register as the source.
- Do not add, remove, or reorder items.
- Do not invent or fabricate content not present in the source items.
- Translate ALL text to {tgt_lang_name}. Do not leave any text in {src_lang_name}."""


class LLMBackend(TranslationBackend):
    """
    Translation backend using llm.professionalize.com OpenAI-compatible API.
    Supports batch translation via numbered prompt packing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        if not self.api_key:
            raise ConfigurationError(
                "LLM_API_KEY environment variable is required for LLMBackend. "
                "Set it to your llm.professionalize.com API key."
            )
        self.base_url = (
            base_url or os.environ.get("LLM_API_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model = model or os.environ.get("TRANSLATE_PRIMARY_MODEL", _DEFAULT_MODEL)
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def is_available(self) -> bool:
        """Check if the API endpoint is reachable."""
        try:
            resp = self._session.get(
                f"{self.base_url}/models",
                timeout=5,
            )
            # 401 means reachable but bad key — still counts as available endpoint
            return resp.status_code in (200, 401)
        except Exception:
            return False

    def list_models(self) -> list[dict]:
        """
        Return models available at this endpoint.
        Calls GET /models and parses data[].id.
        Returns [] on auth failure or network error (with a warning).
        Result is cached per instance to avoid repeated API calls.
        """
        if hasattr(self, "_models_cache"):
            return self._models_cache
        try:
            resp = self._session.get(f"{self.base_url}/models", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # OpenAI-compatible: {"data": [{"id": "...", ...}, ...]}
                # Also accept flat list: [{"id": "..."}, ...]
                items = data.get("data", data) if isinstance(data, dict) else data
                models = [{"id": m["id"]} for m in items if isinstance(m, dict) and "id" in m]
                self._models_cache = models
                return models
            elif resp.status_code == 401:
                logger.warning(
                    "LLM backend: /models returned 401 — API key may be invalid; "
                    "cannot list models"
                )
            else:
                logger.warning(
                    f"LLM backend: /models returned HTTP {resp.status_code}; "
                    "cannot list models"
                )
        except Exception as exc:
            logger.warning(f"LLM backend: failed to list models: {exc}")
        self._models_cache = []
        return []

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """Translate a single text segment."""
        from translator import LOCALE_NAMES

        src_name = LOCALE_NAMES.get(src_lang, src_lang.upper())
        tgt_name = LOCALE_NAMES.get(tgt_lang, tgt_lang.upper())

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            src_lang_name=src_name,
            tgt_lang_name=tgt_name,
            context_block="",
        )

        def _call():
            try:
                resp = self._session.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": text},
                        ],
                        "temperature": self.temperature,
                        "max_tokens": min(16384, max(4096, len(text.encode("utf-8")) // 4)),
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    if content is None:
                        raise BackendUnavailableError("API returned null content")
                    return content.strip()
                elif resp.status_code in (429, 500, 502, 503, 504):
                    raise BackendUnavailableError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                else:
                    raise BackendUnavailableError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
            except requests.exceptions.ConnectionError as e:
                raise BackendUnavailableError(f"Connection failed: {e}") from e
            except requests.exceptions.Timeout as e:
                raise BackendUnavailableError(f"Request timed out: {e}") from e

        return _retry_with_backoff(_call, self.max_retries)

    def translate_with_context(
        self,
        text: str,
        src_lang: str,
        tgt_lang: str,
        document_title: str = "",
        heading_outline: str = "",
        prev_segment: str = "",
    ) -> str:
        """Translate a single text segment with document-level context."""
        from translator import LOCALE_NAMES

        src_name = LOCALE_NAMES.get(src_lang, src_lang.upper())
        tgt_name = LOCALE_NAMES.get(tgt_lang, tgt_lang.upper())

        context_block = ""
        if document_title:
            context_block += f"\n\nDocument title: {document_title}"
        if heading_outline:
            context_block += f"\nDocument outline:\n{heading_outline}"
        if prev_segment:
            context_block += (
                f"\n\nPreceding translated segment (for continuity only — "
                f"do not re-translate it):\n{prev_segment[:300]}"
            )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            src_lang_name=src_name,
            tgt_lang_name=tgt_name,
            context_block=context_block,
        )

        def _call():
            try:
                resp = self._session.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": text},
                        ],
                        "temperature": self.temperature,
                        "max_tokens": min(16384, max(4096, len(text.encode("utf-8")) // 4)),
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    if content is None:
                        raise BackendUnavailableError("API returned null content")
                    return content.strip()
                elif resp.status_code in (429, 500, 502, 503, 504):
                    raise BackendUnavailableError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                else:
                    raise BackendUnavailableError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
            except requests.exceptions.ConnectionError as e:
                raise BackendUnavailableError(f"Connection failed: {e}") from e
            except requests.exceptions.Timeout as e:
                raise BackendUnavailableError(f"Request timed out: {e}") from e

        return _retry_with_backoff(_call, self.max_retries)

    def translate_batch(self, texts: list[str], src_lang: str, tgt_lang: str) -> list[str]:
        """
        Translate a batch using numbered prompt packing.
        Packs up to 20 segments per LLM call.
        Falls back to per-segment translation if response parsing fails.
        """
        if not texts:
            return []

        from translator import LOCALE_NAMES

        src_name = LOCALE_NAMES.get(src_lang, src_lang.upper())
        tgt_name = LOCALE_NAMES.get(tgt_lang, tgt_lang.upper())

        results = []
        batch_size = 20

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results = self._translate_batch_chunk(batch, src_name, tgt_name)
            results.extend(batch_results)

        return results

    def _translate_batch_chunk(
        self, texts: list[str], src_name: str, tgt_name: str
    ) -> list[str]:
        """Translate a chunk of texts using numbered prompt."""
        if len(texts) == 1:
            from translator import LOCALE_NAMES

            tgt_lang = next(
                (k for k, v in LOCALE_NAMES.items() if v == tgt_name), tgt_name.lower()
            )
            src_lang = next(
                (k for k, v in LOCALE_NAMES.items() if v == src_name), "en"
            )
            return [self.translate(texts[0], src_lang, tgt_lang)]

        system_prompt = BATCH_SYSTEM_PROMPT_TEMPLATE.format(
            src_lang_name=src_name,
            tgt_lang_name=tgt_name,
        )
        numbered_input = "\n".join(f"{j + 1}. {t}" for j, t in enumerate(texts))

        def _call():
            try:
                resp = self._session.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": numbered_input},
                        ],
                        "temperature": self.temperature,
                        "max_tokens": min(16384, max(4096, len(numbered_input.encode("utf-8")) // 4)),
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    if content is None:
                        raise BackendUnavailableError("API returned null content")
                    return content.strip()
                elif resp.status_code in (429, 500, 502, 503, 504):
                    raise BackendUnavailableError(f"HTTP {resp.status_code}")
                else:
                    raise BackendUnavailableError(f"HTTP {resp.status_code}")
            except requests.exceptions.ConnectionError as e:
                raise BackendUnavailableError(str(e)) from e
            except requests.exceptions.Timeout as e:
                raise BackendUnavailableError(str(e)) from e

        raw_response = _retry_with_backoff(_call, self.max_retries)
        parsed = _parse_numbered_response(raw_response, len(texts))
        if parsed and len(parsed) == len(texts):
            return parsed

        # Fallback: per-segment translation
        logger.warning(
            "Batch response parsing failed; falling back to per-segment translation"
        )
        from translator import LOCALE_NAMES

        src_lang = next(
            (k for k, v in LOCALE_NAMES.items() if v == src_name), "en"
        )
        tgt_lang = next(
            (k for k, v in LOCALE_NAMES.items() if v == tgt_name), tgt_name.lower()
        )
        return [self.translate(t, src_lang, tgt_lang) for t in texts]

    def get_model_info(self) -> dict:
        return {"backend": "llm.professionalize.com", "model": self.model}


def _parse_numbered_response(response: str, expected_count: int) -> list[str] | None:
    """
    Parse a numbered response like:
    1. First translation
    2. Second translation
    Returns list of translations, or None if parsing fails.
    """
    lines = response.strip().split("\n")
    results: dict[int, str] = {}
    current_idx: Optional[int] = None
    current_lines: list[str] = []

    for line in lines:
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            if current_idx is not None:
                results[current_idx] = "\n".join(current_lines).strip()
            current_idx = int(m.group(1))
            current_lines = [m.group(2)]
        elif current_idx is not None:
            current_lines.append(line)

    if current_idx is not None:
        results[current_idx] = "\n".join(current_lines).strip()

    if len(results) != expected_count:
        return None

    try:
        return [results[i + 1] for i in range(expected_count)]
    except KeyError:
        return None
